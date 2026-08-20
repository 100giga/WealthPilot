"""Milestone 3: memory consolidation ("Dreaming").

Left uncurated, months of sessions accumulate duplicate facts and stale
information. Consolidation is an offline batch job, run between sessions,
that merges near-duplicate entries and prunes what has gone stale — in
direct analogy to how sleep consolidates human memory overnight.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from wealth_pilot.memory.embeddings import cosine_similarity, embed
from wealth_pilot.memory.store import MemoryStore, SemanticFact

SIMILARITY_THRESHOLD = 0.5


@dataclass
class ConsolidationReport:
    pruned_expired: list[str]
    merged_groups: list[list[str]]  # each inner list: fact keys merged into the first


def consolidate(store: MemoryStore, client_id: str, *, now: float | None = None) -> ConsolidationReport:
    now = now if now is not None else time.time()
    facts = store.facts(client_id)

    pruned_expired = [f.key for f in facts if f.expires_at is not None and f.expires_at < now]
    facts = [f for f in facts if f.key not in pruned_expired]

    merged_groups: list[list[str]] = []
    remaining = list(facts)
    survivors: list[SemanticFact] = []
    while remaining:
        anchor = remaining.pop(0)
        group = [anchor]
        still_remaining = []
        anchor_vec = embed(anchor.value)
        for other in remaining:
            if cosine_similarity(anchor_vec, embed(other.value)) >= SIMILARITY_THRESHOLD:
                group.append(other)
            else:
                still_remaining.append(other)
        remaining = still_remaining
        best = max(group, key=lambda f: (f.confidence, f.updated_at))
        survivors.append(best)
        if len(group) > 1:
            merged_groups.append([f.key for f in group])

    data = store._load_semantic()  # noqa: SLF001 - consolidation is an internal-maintenance operation
    keep_ids = {f.id for f in survivors}
    data = {
        fid: v
        for fid, v in data.items()
        if v["client_id"] != client_id or fid in keep_ids
    }
    store._save_semantic(data)  # noqa: SLF001

    return ConsolidationReport(pruned_expired=pruned_expired, merged_groups=merged_groups)
