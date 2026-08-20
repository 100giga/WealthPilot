"""Milestone 1: the self-repair loop.

Generate an output, validate it, and — if validation fails — feed the exact
validation error back into the model as new context rather than simply
asking again. Capped at a small number of attempts; beyond that, escalate
to a human rather than loop indefinitely. This is "the smallest agent you
will build": generate, check, act on the check, repeat.
"""

from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from wealth_pilot.llm.client import LLMClient

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class EscalateToHuman(Exception):
    """Raised when the repair loop exhausts its attempt budget."""

    def __init__(self, schema_name: str, attempts: int, last_error: str) -> None:
        self.schema_name = schema_name
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(
            f"Escalating to human after {attempts} failed attempts to produce a valid "
            f"{schema_name}: {last_error}"
        )


def _extract_json(text: str) -> str:
    """Models often wrap JSON in prose or code fences; pull out the object."""

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1)
    brace = re.search(r"\{.*\}", text, re.DOTALL)
    return brace.group(0) if brace else text


def generate_structured(
    client: LLMClient,
    prompt: str,
    schema: type[SchemaT],
    *,
    max_attempts: int = 3,
) -> SchemaT:
    instruction = (
        f"{prompt}\n\nRespond with ONLY a single JSON object matching this schema "
        f"(no prose, no markdown fences): {schema.model_json_schema()}"
    )
    last_error = ""
    for attempt in range(1, max_attempts + 1):
        raw = client.chat(instruction)
        try:
            candidate = json.loads(_extract_json(raw))
            return schema.model_validate(candidate)
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = str(exc)
            instruction = (
                "That response failed validation with this exact error:\n"
                f"{last_error}\n\n"
                "Return ONLY a corrected JSON object, no words, no markdown fences."
            )
    raise EscalateToHuman(schema.__name__, max_attempts, last_error)
