"""Milestone 6: supervisor routing with a hard loop-back cap.

The supervisor routes by the current state of the task, not a fixed
pipeline — including sending work backward when the Compliance Reviewer
rejects a proposal. "Until it's good" is explicitly rejected as a
termination condition: MAX_REVISIONS caps how many times the Strategist
can be sent back before the task escalates to a human instead.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from wealth_pilot.team.agents import compliance_reviewer, portfolio_strategist, research_analyst, risk_assessor
from wealth_pilot.team.state import MAX_REVISIONS, TeamState


def route(state: TeamState) -> str:
    if not state["research_findings"]:
        return "research_analyst"
    if state["risk_notes"] is None:
        return "risk_assessor"
    if state["recommendation"] is None:
        return "portfolio_strategist"
    review = state["compliance_review"]
    # a revised recommendation invalidates the previous review — re-review
    # rather than trusting a decision made about a different proposal
    if review is None or review["reviewed_revision"] != state["revision_count"]:
        return "compliance_reviewer"
    if not review["approved"]:
        if state["revision_count"] < MAX_REVISIONS:
            return "portfolio_strategist"
        return "human_escalation"
    return "done"


def supervisor_node(state: TeamState) -> dict[str, Any]:
    next_agent = route(state)
    return {"next_agent": next_agent, "log": [f"supervisor: routing to {next_agent}"]}


def human_escalation_node(state: TeamState) -> dict[str, Any]:
    return {"status": "escalated_to_human", "log": ["escalated: revision cap reached without compliance approval"]}


def done_node(state: TeamState) -> dict[str, Any]:
    return {"status": "approved", "log": ["team run complete: recommendation approved"]}


def build_team_graph():
    graph = StateGraph(TeamState)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("research_analyst", research_analyst)
    graph.add_node("risk_assessor", risk_assessor)
    graph.add_node("portfolio_strategist", portfolio_strategist)
    graph.add_node("compliance_reviewer", compliance_reviewer)
    graph.add_node("human_escalation", human_escalation_node)
    graph.add_node("done", done_node)

    graph.add_edge(START, "supervisor")
    for specialist in ("research_analyst", "risk_assessor", "portfolio_strategist", "compliance_reviewer"):
        graph.add_edge(specialist, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        lambda state: state["next_agent"],
        {
            "research_analyst": "research_analyst",
            "risk_assessor": "risk_assessor",
            "portfolio_strategist": "portfolio_strategist",
            "compliance_reviewer": "compliance_reviewer",
            "human_escalation": "human_escalation",
            "done": "done",
        },
    )
    graph.add_edge("human_escalation", END)
    graph.add_edge("done", END)
    return graph.compile()


def run_team(client_id: str, brief: str) -> TeamState:
    graph = build_team_graph()
    initial: TeamState = {
        "client_id": client_id,
        "brief": brief,
        "research_findings": [],
        "risk_notes": None,
        "recommendation": None,
        "compliance_review": None,
        "revision_count": 0,
        "next_agent": "",
        "status": "in_progress",
        "log": [],
    }
    return graph.invoke(initial, config={"recursion_limit": 50})
