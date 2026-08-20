"""Milestone 4: proving RAG is actually good.

A RAG system can be confident, fluent and completely wrong. A golden set —
questions paired with the specific document ids that should be retrieved —
is the standard for measuring retrieval quality directly, rather than
judging an answer by how convincing it sounds. A pipeline is only "better"
than another when proven on the same test set, not because its demos
look more convincing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from wealth_pilot.rag.index import Document


@dataclass
class GoldenExample:
    query: str
    # prefixes are enough (e.g. a source-file stem) — chunk counts can
    # shift as chunking strategy changes without invalidating the golden set
    expected_doc_ids: list[str]


@dataclass
class EvalReport:
    recall_at_k: float
    precision_at_k: float
    mrr_at_k: float
    per_query: list[dict]


def evaluate(
    golden_set: list[GoldenExample],
    retrieve_fn: Callable[[str, int], list[tuple[Document, float]]],
    *,
    k: int = 5,
) -> EvalReport:
    per_query = []
    recalls, precisions, reciprocal_ranks = [], [], []

    def matches(doc_id: str, expected_prefixes: set[str]) -> str | None:
        return next((p for p in expected_prefixes if doc_id.startswith(p)), None)

    for example in golden_set:
        results = retrieve_fn(example.query, k)
        retrieved_ids = [doc.id for doc, _ in results]
        expected = set(example.expected_doc_ids)

        hit_prefixes = {matches(doc_id, expected) for doc_id in retrieved_ids} - {None}
        recall = len(hit_prefixes) / len(expected) if expected else 0.0
        precision = (
            sum(1 for doc_id in retrieved_ids if matches(doc_id, expected)) / len(retrieved_ids)
            if retrieved_ids
            else 0.0
        )
        rr = 0.0
        for rank, doc_id in enumerate(retrieved_ids, start=1):
            if matches(doc_id, expected):
                rr = 1.0 / rank
                break

        recalls.append(recall)
        precisions.append(precision)
        reciprocal_ranks.append(rr)
        per_query.append(
            {"query": example.query, "expected": list(expected), "retrieved": retrieved_ids, "recall": recall, "precision": precision, "rr": rr}
        )

    n = len(golden_set) or 1
    return EvalReport(
        recall_at_k=sum(recalls) / n,
        precision_at_k=sum(precisions) / n,
        mrr_at_k=sum(reciprocal_ranks) / n,
        per_query=per_query,
    )
