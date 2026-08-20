"""Milestone 5: an orchestrated LangGraph workflow with checkpointing.

A bare reasoning loop doesn't know when to stop, is opaque, and loses
everything on a crash. This graph has named stages, pauses for a human
before any plan is executed, and — because state is checkpointed at every
step — a crash mid-run resumes from the last checkpoint rather than
starting over.

Chain-vs-graph discipline: this task genuinely needs a human pause that
may last days and a capped revision loop-back, so a graph (not a plain
chain) is the right call here.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from wealth_pilot.graph.state import MAX_REVISIONS, PlanningState
from wealth_pilot.llm.schemas import FinancialProfile, InvestmentPlan, RiskAssessment


def _assess_risk(profile: dict[str, Any]) -> dict[str, Any]:
    tolerance = profile["risk_tolerance"]
    horizon = profile["investment_horizon_years"]
    base = {"conservative": 30, "moderate": 55, "aggressive": 75}[tolerance]
    # a longer horizon can absorb more volatility
    horizon_bonus = min(15, horizon // 2)
    equity_pct = min(90, base + horizon_bonus)
    score = min(100, equity_pct + 10)
    assessment = RiskAssessment(
        score=score,
        tolerance=tolerance,
        rationale=f"{tolerance} tolerance with a {horizon}-year horizon supports {equity_pct}% equity exposure",
        recommended_equity_allocation_pct=equity_pct,
    )
    return assessment.model_dump()


def _draft_plan(profile: dict[str, Any], risk_assessment: dict[str, Any]) -> dict[str, Any]:
    equity = risk_assessment["recommended_equity_allocation_pct"]
    gold = 10
    debt = max(0, 100 - equity - gold)
    monthly_contribution = round(max(0.0, profile["annual_income"] / 12 - profile["monthly_expenses"]) * 0.3, 2)
    plan = InvestmentPlan(
        summary=f"{equity}% equity / {debt}% debt / {gold}% gold, targeting {profile['primary_goal']}",
        monthly_contribution=monthly_contribution,
        allocation={"equity": equity, "debt": debt, "gold": gold},
        requires_human_approval=True,
    )
    return plan.model_dump()


def risk_profile_node(state: PlanningState) -> dict[str, Any]:
    assessment = _assess_risk(state["profile"])
    return {"risk_assessment": assessment, "log": [f"risk assessed: score={assessment['score']}"]}


def draft_plan_node(state: PlanningState) -> dict[str, Any]:
    plan = _draft_plan(state["profile"], state["risk_assessment"])
    return {"draft_plan": plan, "status": "awaiting_approval", "log": [f"draft plan ready: {plan['summary']}"]}


def execute_plan_node(state: PlanningState) -> dict[str, Any]:
    decision = state.get("human_decision")
    if decision == "approved":
        return {"status": "executed", "log": ["plan approved and executed"]}
    if decision == "rejected":
        if state["revision_count"] >= MAX_REVISIONS:
            return {"status": "escalated_to_human", "log": ["max revision rounds reached — escalating to a human"]}
        return {
            "status": "drafting",
            "revision_count": state["revision_count"] + 1,
            "human_decision": None,
            "log": [f"plan rejected — starting revision {state['revision_count'] + 1}"],
        }
    return {"status": "awaiting_approval", "log": ["execute_plan reached with no human_decision — should not happen"]}


def _route_after_execute(state: PlanningState) -> str:
    return "draft_plan" if state["status"] == "drafting" else END


def build_graph(checkpointer: SqliteSaver):
    graph = StateGraph(PlanningState)
    graph.add_node("risk_profile", risk_profile_node)
    graph.add_node("draft_plan", draft_plan_node)
    graph.add_node("execute_plan", execute_plan_node)

    graph.add_edge(START, "risk_profile")
    graph.add_edge("risk_profile", "draft_plan")
    graph.add_edge("draft_plan", "execute_plan")
    graph.add_conditional_edges("execute_plan", _route_after_execute, {"draft_plan": "draft_plan", END: END})

    # The checkpointer must exist before the interrupt point is wired in,
    # or the graph silently fails to pause at all.
    return graph.compile(checkpointer=checkpointer, interrupt_before=["execute_plan"])


def sqlite_checkpointer(path: Path) -> SqliteSaver:
    conn = sqlite3.connect(str(path), check_same_thread=False)
    return SqliteSaver(conn)


def initial_state(client_id: str, profile: FinancialProfile) -> PlanningState:
    return {
        "client_id": client_id,
        "profile": profile.model_dump(),
        "risk_assessment": None,
        "draft_plan": None,
        "human_decision": None,
        "revision_count": 0,
        "status": "drafting",
        "log": [],
    }


def start_workflow(graph, client_id: str, profile: FinancialProfile) -> PlanningState:
    config = {"configurable": {"thread_id": client_id}}
    graph.invoke(initial_state(client_id, profile), config=config)
    return graph.get_state(config).values


def resume_workflow(graph, client_id: str, decision: str) -> PlanningState:
    """decision: 'approved' or 'rejected'. Resumes from the checkpoint —
    no re-running of risk_profile or draft_plan.
    """

    config = {"configurable": {"thread_id": client_id}}
    graph.update_state(config, {"human_decision": decision})
    graph.invoke(None, config=config)
    return graph.get_state(config).values
