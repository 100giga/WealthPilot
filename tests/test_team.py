from wealth_pilot.team.state import AGENT_SCOPES, TeamState, scoped
from wealth_pilot.team.supervisor import run_team


def test_full_team_run_reaches_a_compliance_decision():
    final = run_team("client-001", "Consider increasing NIFTY50 exposure")
    assert final["compliance_review"] is not None
    assert final["status"] in {"approved", "escalated_to_human"}


def test_first_proposal_is_rejected_then_revised_and_approved():
    # client-001's starting portfolio is 70% equity; the strategist's first
    # proposal (+15%) exceeds the compliance ceiling and must be revised down.
    final = run_team("client-001", "Consider increasing NIFTY50 exposure")
    assert final["revision_count"] == 1
    assert final["status"] == "approved"
    assert final["recommendation"]["target_equity_pct"] <= 80


def test_research_and_risk_findings_are_populated_before_recommendation():
    final = run_team("client-001", "review NIFTY50 and GOLD_ETF exposure")
    assert len(final["research_findings"]) >= 1
    assert final["risk_notes"] is not None


def test_scoped_decorator_rejects_out_of_scope_writes():
    @scoped("research_analyst")
    def bad_agent(state: TeamState) -> dict:
        return {"recommendation": {"oops": True}}  # not in research_analyst's scope

    try:
        bad_agent({"brief": "x"})
        assert False, "expected a scope violation"
    except RuntimeError as exc:
        assert "out-of-scope" in str(exc)


def test_agent_scopes_cover_every_specialist():
    assert set(AGENT_SCOPES) == {"research_analyst", "risk_assessor", "portfolio_strategist", "compliance_reviewer"}
