"""Milestone 4: reranking.

A fast, broad first-pass retrieval is optimized for recall, not precision,
and often buries the actual best answer partway down the list. A second,
slower and more accurate pass re-scores only the top candidates. In
production this is usually a cross-encoder; here it's a transparent
lexical + dense heuristic — the interface (`rerank`) is what matters, so
swapping in a real cross-encoder later only touches this one function.
"""

from __future__ import annotations

from wealth_pilot.memory.embeddings import cosine_similarity, embed
from wealth_pilot.rag.index import Document


def _lexical_overlap(query: str, text: str) -> float:
    q_tokens = set(query.lower().split())
    d_tokens = set(text.lower().split())
    if not q_tokens or not d_tokens:
        return 0.0
    return len(q_tokens & d_tokens) / len(q_tokens | d_tokens)


def rerank(query: str, candidates: list[Document], top_k: int = 5) -> list[tuple[Document, float]]:
    q_vec = embed(query)
    scored = []
    for doc in candidates:
        dense = cosine_similarity(q_vec, embed(doc.text))
        lexical = _lexical_overlap(query, doc.text)
        # weighted toward dense similarity; lexical breaks ties on exact-term matches
        scored.append((doc, 0.7 * dense + 0.3 * lexical))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:top_k]
