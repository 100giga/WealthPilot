"""Shared state for Milestone 6's specialist team."""

from __future__ import annotations

from operator import add
from typing import Annotated, Any, TypedDict

MAX_REVISIONS = 2

# Each specialist writes only to its own scoped keys — the same discipline
# that keeps a supervised team debuggable instead of a free-for-all on
# shared state.
AGENT_SCOPES: dict[str, set[str]] = {
    "research_analyst": {"research_findings"},
    "risk_assessor": {"risk_notes"},
    "portfolio_strategist": {"recommendation", "revision_count"},
    "compliance_reviewer": {"compliance_review"},
}


class TeamState(TypedDict):
    client_id: str
    brief: str
    research_findings: Annotated[list[dict[str, Any]], add]
    risk_notes: dict[str, Any] | None
    recommendation: dict[str, Any] | None
    compliance_review: dict[str, Any] | None
    revision_count: int
    next_agent: str
    status: str
    log: Annotated[list[str], add]


def scoped(agent_name: str):
    """Decorator: raise if a specialist tries to write outside its scope."""

    allowed = AGENT_SCOPES[agent_name]

    def decorator(fn):
        def wrapper(state: TeamState) -> dict[str, Any]:
            update = fn(state)
            offending = set(update) - allowed - {"log"}
            if offending:
                raise RuntimeError(f"{agent_name} tried to write out-of-scope keys: {offending}")
            return update

        wrapper.__name__ = fn.__name__
        return wrapper

    return decorator
