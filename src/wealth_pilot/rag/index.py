"""Milestone 4: hybrid search.

Dense (semantic) search handles synonyms and paraphrase but is weak on
exact identifiers — a search for "INV-2026-0417" can retrieve a
semantically similar but factually wrong document. Sparse (BM25) search
is excellent for exact codes and IDs but brittle to vocabulary mismatch.
In a domain with exact identifiers (fund codes, ISINs), combining both is
a requirement, not an optimization. Reciprocal Rank Fusion combines the
two ranked lists by position rather than comparing incompatible raw scores.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from wealth_pilot.memory.embeddings import cosine_similarity, embed


@dataclass
class Document:
    id: str
    text: str
    metadata: dict


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text.lower())


class HybridIndex:
    def __init__(self, documents: list[Document]) -> None:
        self.documents = documents
        self._corpus_tokens = [_tokenize(d.text) for d in documents]
        self._bm25 = BM25Okapi(self._corpus_tokens) if documents else None
        self._dense_vectors = [embed(d.text) for d in documents]

    def _sparse_ranked_ids(self, query: str) -> list[str]:
        if not self._bm25:
            return []
        scores = self._bm25.get_scores(_tokenize(query))
        order = sorted(range(len(self.documents)), key=lambda i: scores[i], reverse=True)
        return [self.documents[i].id for i in order if scores[i] > 0]

    def _dense_ranked_ids(self, query: str) -> list[str]:
        q_vec = embed(query)
        scored = [(d.id, cosine_similarity(q_vec, v)) for d, v in zip(self.documents, self._dense_vectors)]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return [doc_id for doc_id, _ in scored]

    def search(self, query: str, top_k: int = 5, *, rrf_k: int = 60) -> list[tuple[Document, float]]:
        """Reciprocal Rank Fusion: score(d) = sum over rankers of 1 / (rrf_k + rank)."""

        sparse_ids = self._sparse_ranked_ids(query)
        dense_ids = self._dense_ranked_ids(query)
        fused: dict[str, float] = {}
        for ranked in (sparse_ids, dense_ids):
            for rank, doc_id in enumerate(ranked, start=1):
                fused[doc_id] = fused.get(doc_id, 0.0) + 1.0 / (rrf_k + rank)
        by_id = {d.id: d for d in self.documents}
        ordered = sorted(fused.items(), key=lambda pair: pair[1], reverse=True)
        return [(by_id[doc_id], score) for doc_id, score in ordered[:top_k]]
