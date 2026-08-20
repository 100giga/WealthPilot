"""Milestone 6: the four specialists.

Each one is deliberately narrow — a Research Analyst that only reads market
data, a Risk Assessor that only reads the client's holdings, a Portfolio
Strategist that only proposes an allocation, and a Compliance Reviewer that
only checks a proposal against policy. None of them can approve their own
work; that separation is what makes the supervisor's routing meaningful.
"""

from __future__ import annotations

import re
from typing import Any

from wealth_pilot.agent.tools import calculate_risk_metrics, get_portfolio, get_quote
from wealth_pilot.rag.index import HybridIndex
from wealth_pilot.rag.loader import load_documents
from wealth_pilot.rag.security import sanitize_for_context
from wealth_pilot.team.state import TeamState, scoped

_KNOWN_SYMBOLS = ["NIFTY50", "SENSEX", "VOO", "GOLD_ETF"]

_EQUITY_APPROVAL_CEILING_PCT = 80  # compliance rule: needs sign-off above this


@scoped("research_analyst")
def research_analyst(state: TeamState) -> dict[str, Any]:
    mentioned = [s for s in _KNOWN_SYMBOLS if s in state["brief"].upper()] or _KNOWN_SYMBOLS[:2]
    findings = [get_quote(symbol) for symbol in mentioned]
    return {"research_findings": findings, "log": [f"research_analyst: quoted {mentioned}"]}


@scoped("risk_assessor")
def risk_assessor(state: TeamState) -> dict[str, Any]:
    portfolio = get_portfolio(state["client_id"])
    metrics = calculate_risk_metrics(portfolio["holdings_pct"])
    return {"risk_notes": metrics, "log": [f"risk_assessor: volatility_score={metrics['volatility_score']}"]}


@scoped("portfolio_strategist")
def portfolio_strategist(state: TeamState) -> dict[str, Any]:
    current_equity = state["risk_notes"]["equity_allocation_pct"]
    was_rejected = state["compliance_review"] is not None and not state["compliance_review"]["approved"]
    target_equity = max(20, current_equity - 15) if was_rejected else min(90, current_equity + 15)
    recommendation = {
        "target_equity_pct": target_equity,
        "target_gold_pct": 10,
        "target_debt_pct": max(0, 100 - target_equity - 10),
        "note": f"proposal for {state['brief']}",
    }
    update: dict[str, Any] = {"recommendation": recommendation, "log": [f"portfolio_strategist: proposed {target_equity}% equity"]}
    if was_rejected:
        update["revision_count"] = state["revision_count"] + 1
    return update


@scoped("compliance_reviewer")
def compliance_reviewer(state: TeamState) -> dict[str, Any]:
    documents = load_documents()
    index = HybridIndex(documents)
    hits = index.search("client KYC status must be current before advisory changes", top_k=1)
    evidence_note = "no policy evidence retrieved"
    if hits:
        doc, _ = hits[0]
        _wrapped, flags = sanitize_for_context(doc.id, doc.text)
        evidence_note = f"checked against {doc.metadata['source']}" + (
            f" (WARNING: {len(flags)} suspicious pattern(s) in retrieved text, ignored)" if flags else ""
        )

    target_equity = state["recommendation"]["target_equity_pct"]
    approved = target_equity <= _EQUITY_APPROVAL_CEILING_PCT
    review = {
        "approved": approved,
        "reason": (
            "within policy"
            if approved
            else f"{target_equity}% equity exceeds the {_EQUITY_APPROVAL_CEILING_PCT}% ceiling without manager sign-off"
        ),
        "evidence": evidence_note,
        # which revision of the recommendation this review covers — lets the
        # supervisor tell "reviewed" apart from "stale, needs re-review"
        "reviewed_revision": state["revision_count"],
    }
    return {"compliance_review": review, "log": [f"compliance_reviewer: approved={approved}"]}
