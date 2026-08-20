"""Milestone 3: persistent memory + semantic index.

CoALA's four kinds of memory, kept genuinely distinct rather than treating
"memory" as one thing a chat history either has or lacks:
  - working:   the live session only — dies when the session ends
  - episodic:  a specific, timestamped thing that happened
  - semantic:  a durable, general fact with no date and no story attached
  - procedural: a reusable strategy for next time

Long-term memory (episodic/semantic/procedural) survives only because of
a deliberate write to disk — never automatically.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from wealth_pilot.config import MEMORY_DIR
from wealth_pilot.memory.embeddings import cosine_similarity, embed


@dataclass
class EpisodicEntry:
    id: str
    client_id: str
    text: str
    timestamp: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SemanticFact:
    id: str
    client_id: str
    key: str
    value: str
    confidence: float
    updated_at: float
    expires_at: float | None = None


class MemoryStore:
    """One store per process; each client's long-term memory is namespaced
    by client_id inside shared files so consolidation can run across clients.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or MEMORY_DIR
        self.root.mkdir(parents=True, exist_ok=True)
        self._episodic_path = self.root / "episodic.jsonl"
        self._semantic_path = self.root / "semantic.json"
        self._procedural_path = self.root / "procedural.json"
        self.working: list[str] = []  # session-scoped, never persisted

    # ---- episodic ----
    def remember_episode(self, client_id: str, text: str, **metadata: Any) -> EpisodicEntry:
        entry = EpisodicEntry(id=str(uuid.uuid4()), client_id=client_id, text=text, timestamp=time.time(), metadata=metadata)
        with self._episodic_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry)) + "\n")
        return entry

    def episodes(self, client_id: str | None = None) -> list[EpisodicEntry]:
        if not self._episodic_path.exists():
            return []
        out = []
        for line in self._episodic_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            if client_id is None or data["client_id"] == client_id:
                out.append(EpisodicEntry(**data))
        return out

    # ---- semantic ----
    def _load_semantic(self) -> dict[str, dict[str, Any]]:
        if not self._semantic_path.exists():
            return {}
        return json.loads(self._semantic_path.read_text(encoding="utf-8"))

    def _save_semantic(self, data: dict[str, dict[str, Any]]) -> None:
        self._semantic_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def remember_fact(
        self, client_id: str, key: str, value: str, confidence: float = 0.9, expires_at: float | None = None
    ) -> SemanticFact:
        data = self._load_semantic()
        fact_id = f"{client_id}:{key}"
        fact = SemanticFact(
            id=fact_id, client_id=client_id, key=key, value=value, confidence=confidence,
            updated_at=time.time(), expires_at=expires_at,
        )
        data[fact_id] = asdict(fact)
        self._save_semantic(data)
        return fact

    def facts(self, client_id: str | None = None) -> list[SemanticFact]:
        data = self._load_semantic()
        out = [SemanticFact(**v) for v in data.values()]
        return [f for f in out if client_id is None or f.client_id == client_id]

    # ---- procedural ----
    def _load_procedural(self) -> list[dict[str, Any]]:
        if not self._procedural_path.exists():
            return []
        return json.loads(self._procedural_path.read_text(encoding="utf-8"))

    def remember_strategy(self, description: str) -> None:
        data = self._load_procedural()
        if description not in {d["description"] for d in data}:
            data.append({"description": description, "learned_at": time.time()})
        self._procedural_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def strategies(self) -> list[str]:
        return [d["description"] for d in self._load_procedural()]

    # ---- semantic search across episodic + semantic memory ----
    def search(self, client_id: str, query: str, top_k: int = 3) -> list[tuple[str, float]]:
        candidates: list[str] = [e.text for e in self.episodes(client_id)]
        candidates += [f"{f.key}: {f.value}" for f in self.facts(client_id)]
        if not candidates:
            return []
        q_vec = embed(query)
        scored = [(text, cosine_similarity(q_vec, embed(text))) for text in candidates]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]
