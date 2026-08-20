"""A tiny, fully local, deterministic embedding function.

Real deployments should swap this for an embedding API or a local model —
the rest of the memory/RAG code only depends on "text -> fixed-length
vector" and cosine similarity, so the swap is a one-function change.
This hashed-character-n-gram approach needs no network and no model
download, which keeps the whole project runnable offline.
"""

from __future__ import annotations

import hashlib

import numpy as np

DIMENSIONS = 256


def embed(text: str, *, n: int = 3) -> np.ndarray:
    vec = np.zeros(DIMENSIONS, dtype=np.float64)
    text = text.lower().strip()
    grams = [text[i : i + n] for i in range(max(len(text) - n + 1, 1))] or [text]
    for gram in grams:
        h = int(hashlib.sha256(gram.encode("utf-8")).hexdigest(), 16)
        vec[h % DIMENSIONS] += 1.0
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom > 0 else 0.0
