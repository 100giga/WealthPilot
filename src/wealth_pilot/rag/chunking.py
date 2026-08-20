"""Milestone 4: chunking strategies.

How a document is split materially affects retrieval quality. Fixed-size
chunking is simple but blind to meaning; recursive chunking applies natural
break separators and is the common production default; markdown chunking
splits on a document's own header hierarchy so section context survives
into each chunk's metadata.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Chunk:
    text: str
    metadata: dict


def fixed_size_chunk(text: str, size: int = 400, overlap: int = 50) -> list[Chunk]:
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(Chunk(text=text[start:end], metadata={"strategy": "fixed", "start": start, "end": end}))
        if end == len(text):
            break
        start = end - overlap
    return chunks


_DEFAULT_SEPARATORS = ["\n\n", "\n", ". ", " "]


def recursive_chunk(text: str, max_size: int = 400, separators: list[str] | None = None) -> list[Chunk]:
    """Applies natural-break separators recursively, falling back to a hard
    split only when nothing more meaningful is available.
    """

    separators = separators if separators is not None else _DEFAULT_SEPARATORS

    def split(fragment: str, seps: list[str]) -> list[str]:
        if len(fragment) <= max_size:
            return [fragment] if fragment.strip() else []
        if not seps:
            return [fragment[i : i + max_size] for i in range(0, len(fragment), max_size)]
        sep, rest = seps[0], seps[1:]
        parts = fragment.split(sep)
        out: list[str] = []
        buffer = ""
        for part in parts:
            candidate = buffer + (sep if buffer else "") + part
            if len(candidate) <= max_size:
                buffer = candidate
            else:
                if buffer:
                    out.append(buffer)
                if len(part) > max_size:
                    out.extend(split(part, rest))
                    buffer = ""
                else:
                    buffer = part
        if buffer:
            out.append(buffer)
        return out

    return [Chunk(text=t, metadata={"strategy": "recursive"}) for t in split(text, separators)]


_HEADER_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


def markdown_structure_chunk(text: str) -> list[Chunk]:
    """Splits on Markdown's own header hierarchy so a chunk's section path
    (e.g. 'Fund Facts > Fees > Expense Ratio') survives into its metadata.
    """

    matches = list(_HEADER_RE.finditer(text))
    if not matches:
        return [Chunk(text=text, metadata={"strategy": "markdown", "path": []})]

    chunks: list[Chunk] = []
    path: list[tuple[int, str]] = []  # (level, title)
    for i, match in enumerate(matches):
        level = len(match.group(1))
        title = match.group(2).strip()
        path = [p for p in path if p[0] < level] + [(level, title)]
        body_start = match.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        if body:
            chunks.append(
                Chunk(text=f"{title}\n{body}", metadata={"strategy": "markdown", "path": [p[1] for p in path]})
            )
    return chunks
