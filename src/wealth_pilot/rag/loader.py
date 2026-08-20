"""Loads the sample fund fact sheets / policy docs and chunks them by
Markdown structure, the common production default for this kind of
document. Kept separate from `index.py` so the chunking strategy used to
build the corpus is a one-line swap (e.g. to `recursive_chunk`).
"""

from __future__ import annotations

from pathlib import Path

from wealth_pilot.config import DATA_DIR
from wealth_pilot.rag.chunking import markdown_structure_chunk
from wealth_pilot.rag.index import Document


def load_documents(directory: Path | None = None) -> list[Document]:
    directory = directory or (DATA_DIR / "fund_fact_sheets")
    documents: list[Document] = []
    for path in sorted(directory.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        for i, chunk in enumerate(markdown_structure_chunk(text)):
            documents.append(
                Document(
                    id=f"{path.stem}#{i}",
                    text=chunk.text,
                    metadata={"source": path.name, **chunk.metadata},
                )
            )
    return documents
