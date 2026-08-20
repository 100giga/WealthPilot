"""Milestone 7: instrumentation (production hardening).

A trace is the recording of one end-to-end run: a tree of spans, each
covering one unit of work, with a start time, end time, and whatever
inputs/outputs are attached. `traced()` always records locally — the
trace *is* the data source for the cost/latency table in
`observability.tracing.summarize` — and additionally forwards to LangFuse
when LANGFUSE_PUBLIC_KEY/SECRET_KEY are set. Missing keys never raise;
they just mean traces don't leave this process.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

from wealth_pilot.config import settings


@dataclass
class Span:
    name: str
    start: float
    end: float
    inputs: dict[str, Any]
    outputs: Any
    error: str | None = None

    @property
    def duration_ms(self) -> float:
        return (self.end - self.start) * 1000


class SpanRecorder:
    """In-process store of every span recorded this run — no external
    service required to build a per-agent cost/latency view.
    """

    def __init__(self) -> None:
        self.spans: list[Span] = []

    def summarize(self) -> dict[str, dict[str, float]]:
        by_name: dict[str, list[Span]] = {}
        for span in self.spans:
            by_name.setdefault(span.name, []).append(span)
        return {
            name: {
                "count": len(spans),
                "total_ms": sum(s.duration_ms for s in spans),
                "avg_ms": sum(s.duration_ms for s in spans) / len(spans),
                "errors": sum(1 for s in spans if s.error),
            }
            for name, spans in by_name.items()
        }


_recorder = SpanRecorder()


def _langfuse_client():
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return None
    try:
        from langfuse import Langfuse
    except ImportError:
        return None
    return Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_base_url,
    )


@contextmanager
def traced(name: str, **inputs: Any) -> Iterator[dict[str, Any]]:
    start = time.monotonic()
    outputs: dict[str, Any] = {}
    error: str | None = None
    try:
        yield outputs
    except Exception as exc:
        error = str(exc)
        raise
    finally:
        end = time.monotonic()
        span = Span(name=name, start=start, end=end, inputs=inputs, outputs=outputs.get("result"), error=error)
        _recorder.spans.append(span)
        client = _langfuse_client()
        if client is not None:
            try:
                client.start_span(name=name, input=inputs, output=outputs.get("result")).end()
            except Exception:
                pass  # tracing must never take down the traced call


def get_recorder() -> SpanRecorder:
    return _recorder


def reset_recorder() -> None:
    _recorder.spans.clear()
