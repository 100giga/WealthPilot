"""Milestone 5: the state that must survive a crash.

Five categories of state a checkpoint must capture: conversation context,
work in progress, agent memory, control/flow state, and external
integration state. `PlanningState` covers the ones this workflow needs.
"""

from __future__ import annotations

from operator import add
from typing import Annotated, Any, TypedDict

MAX_REVISIONS = 2


class PlanningState(TypedDict):
    client_id: str
    profile: dict[str, Any]
    risk_assessment: dict[str, Any] | None
    draft_plan: dict[str, Any] | None
    human_decision: str | None  # "approved" | "rejected" | None
    revision_count: int
    status: str  # "drafting" | "awaiting_approval" | "executed" | "rejected"
    log: Annotated[list[str], add]
