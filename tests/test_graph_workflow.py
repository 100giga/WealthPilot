from pathlib import Path

from wealth_pilot.graph.state import MAX_REVISIONS
from wealth_pilot.graph.workflow import build_graph, resume_workflow, sqlite_checkpointer, start_workflow
from wealth_pilot.llm.schemas import FinancialProfile

PROFILE = FinancialProfile(
    full_name="Asha Rao", annual_income=1_800_000, monthly_expenses=60_000, current_savings=900_000,
    risk_tolerance="aggressive", investment_horizon_years=20, primary_goal="early retirement", currency="INR",
)


def test_workflow_pauses_before_execute_for_human_approval(tmp_path: Path):
    checkpointer = sqlite_checkpointer(tmp_path / "checkpoints.sqlite")
    graph = build_graph(checkpointer)
    state = start_workflow(graph, "client-approval-test", PROFILE)
    assert state["status"] == "awaiting_approval"
    assert state["draft_plan"] is not None
    assert state["human_decision"] is None


def test_approval_resumes_and_executes_without_rerunning_earlier_nodes(tmp_path: Path):
    checkpointer = sqlite_checkpointer(tmp_path / "checkpoints.sqlite")
    graph = build_graph(checkpointer)
    start_workflow(graph, "client-approve", PROFILE)
    final = resume_workflow(graph, "client-approve", "approved")
    assert final["status"] == "executed"
    assert final["revision_count"] == 0


def test_rejection_loops_back_to_draft_plan_within_cap(tmp_path: Path):
    checkpointer = sqlite_checkpointer(tmp_path / "checkpoints.sqlite")
    graph = build_graph(checkpointer)
    start_workflow(graph, "client-revise", PROFILE)
    after_first_rejection = resume_workflow(graph, "client-revise", "rejected")
    assert after_first_rejection["status"] == "awaiting_approval"
    assert after_first_rejection["revision_count"] == 1

    final = resume_workflow(graph, "client-revise", "approved")
    assert final["status"] == "executed"


def test_revision_cap_escalates_to_human_instead_of_looping_forever(tmp_path: Path):
    checkpointer = sqlite_checkpointer(tmp_path / "checkpoints.sqlite")
    graph = build_graph(checkpointer)
    client_id = "client-cap"
    start_workflow(graph, client_id, PROFILE)
    for _ in range(MAX_REVISIONS):
        resume_workflow(graph, client_id, "rejected")
    final = resume_workflow(graph, client_id, "rejected")
    assert final["status"] == "escalated_to_human"


def test_crash_recovery_resumes_from_last_checkpoint_with_a_fresh_process(tmp_path: Path):
    db_path = tmp_path / "checkpoints.sqlite"
    checkpointer_1 = sqlite_checkpointer(db_path)
    graph_1 = build_graph(checkpointer_1)
    client_id = "client-crash"
    start_workflow(graph_1, client_id, PROFILE)
    # simulate a crash: graph_1 / checkpointer_1 are simply abandoned here,
    # never told the run finished.

    checkpointer_2 = sqlite_checkpointer(db_path)  # a fresh "process" opens the same file
    graph_2 = build_graph(checkpointer_2)
    final = resume_workflow(graph_2, client_id, "approved")
    assert final["status"] == "executed"
    assert final["draft_plan"] is not None  # never had to be regenerated
