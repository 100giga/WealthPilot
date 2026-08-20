#!/usr/bin/env python
"""End-to-end walkthrough of every milestone, offline (mock LLM, no API keys).

    python examples/demo.py

Set LLM_PROVIDER=openai|anthropic|groq (and the matching *_API_KEY) in .env
to run Milestones 1-2 against a real model instead of the mock.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from wealth_pilot.agent.single_agent import PortfolioAnalystAgent
from wealth_pilot.agent.tools import ToolRegistry
from wealth_pilot.graph.workflow import build_graph, resume_workflow, sqlite_checkpointer, start_workflow
from wealth_pilot.llm.client import LLMClient, MockProvider
from wealth_pilot.llm.repair import generate_structured
from wealth_pilot.llm.schemas import FinancialProfile
from wealth_pilot.memory.consolidate import consolidate
from wealth_pilot.memory.store import MemoryStore
from wealth_pilot.observability.tracing import get_recorder, reset_recorder, traced
from wealth_pilot.rag.evaluate import GoldenExample, evaluate
from wealth_pilot.rag.index import HybridIndex
from wealth_pilot.rag.loader import load_documents
from wealth_pilot.rag.rerank import rerank
from wealth_pilot.rag.security import sanitize_for_context
from wealth_pilot.team.supervisor import run_team


def banner(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def milestone_1_structured_intake() -> FinancialProfile:
    banner("Milestone 1 - provider-agnostic client + structured intake")
    intake_json = FinancialProfile(
        full_name="Asha Rao", annual_income=1_800_000, monthly_expenses=60_000,
        current_savings=900_000, risk_tolerance="aggressive", investment_horizon_years=20,
        primary_goal="early retirement", currency="INR",
    ).model_dump_json()
    client = LLMClient(provider=MockProvider(script=[intake_json]), system_prompt="Intake assistant.")
    with traced("milestone_1.structured_intake"):
        profile = generate_structured(client, "Extract Asha's financial profile.", FinancialProfile)
    print(f"validated profile: {profile.model_dump()}")
    return profile


def milestone_2_single_agent() -> None:
    banner("Milestone 2 - tool-enabled single agent (capped ReAct loop)")
    script = [
        json.dumps({"thought": "check the client's holdings", "action": {"tool": "get_portfolio", "arguments": {"client_id": "client-001"}}}),
        json.dumps({"thought": "assess risk from those holdings", "action": {"tool": "calculate_risk_metrics", "arguments": {"holdings_pct": {"NIFTY50": 40, "GOLD_ETF": 10, "VOO": 30, "CASH": 20}}}}),
        json.dumps({"thought": "enough to answer", "final_answer": "client-001 is 70% equity with a volatility score of 12.6 - moderately aggressive."}),
    ]
    agent = PortfolioAnalystAgent(client=LLMClient(provider=MockProvider(script=script)), registry=ToolRegistry())
    with traced("milestone_2.agent_run"):
        answer, steps = agent.run("How risky is client-001's current portfolio?")
    print(f"agent answer: {answer}")
    print(f"steps taken: {len(steps)}")


def milestone_3_memory(profile: FinancialProfile) -> None:
    banner("Milestone 3 - persistent memory + semantic index")
    with tempfile.TemporaryDirectory() as tmp:
        store = MemoryStore(root=Path(tmp))
        store.remember_episode("client-001", f"Client goal: {profile.primary_goal}, horizon {profile.investment_horizon_years}y")
        store.remember_fact("client-001", "risk_tolerance_a", "User is comfortable with an aggressive risk tolerance", confidence=0.7)
        store.remember_fact("client-001", "risk_tolerance_b", "The client's risk tolerance is aggressive", confidence=0.95)
        report = consolidate(store, "client-001")
        print(f"consolidation merged groups: {report.merged_groups}")
        hits = store.search("client-001", "what is the client's investment horizon?", top_k=1)
        print(f"semantic recall: {hits}")


def milestone_4_rag() -> None:
    banner("Milestone 4 - production RAG + evaluation baseline")
    documents = load_documents()
    index = HybridIndex(documents)
    query = "How often must a moderate risk client re-verify KYC?"
    candidates = [doc for doc, _ in index.search(query, top_k=10)]
    top = rerank(query, candidates, top_k=1)[0][0]
    print(f"top reranked source: {top.metadata['source']}")

    flagged = next(d for d in documents if d.metadata["source"] == "vendor_proposal_flagged.md" and "Ignore all" in d.text)
    _wrapped, flags = sanitize_for_context(flagged.id, flagged.text)
    print(f"security scan on vendor doc: {[f.category for f in flags]}")

    golden = json.loads((Path(__file__).resolve().parents[1] / "data" / "golden_set.json").read_text())
    report = evaluate([GoldenExample(**g) for g in golden], index.search, k=5)
    print(f"golden-set eval: recall@5={report.recall_at_k:.2f} mrr@5={report.mrr_at_k:.2f}")


def milestone_5_graph(profile: FinancialProfile) -> None:
    banner("Milestone 5 - orchestrated LangGraph workflow with checkpointing")
    with tempfile.TemporaryDirectory() as tmp:
        checkpointer = sqlite_checkpointer(Path(tmp) / "checkpoints.sqlite")
        try:
            graph = build_graph(checkpointer)
            state = start_workflow(graph, "client-001", profile)
            print(f"paused for human approval: status={state['status']}, plan={state['draft_plan']['summary']}")
            final = resume_workflow(graph, "client-001", "approved")
            print(f"resumed after approval: status={final['status']}")
        finally:
            checkpointer.conn.close()  # release the sqlite file before the temp dir is removed


def milestone_6_team() -> None:
    banner("Milestone 6 - specialized multi-agent team + MCP integration")
    final = run_team("client-001", "Consider increasing NIFTY50 exposure")
    print(f"team outcome: status={final['status']}, revisions={final['revision_count']}")
    print(f"compliance review: {final['compliance_review']}")
    print("log:")
    for line in final["log"]:
        print(f"  - {line}")
    print("(MCP tools are exposed separately - run `python -m wealth_pilot.team.mcp_server`)")


def milestone_7_observability() -> None:
    banner("Milestone 7 - observability & failure injection (production hardening)")
    reset_recorder()
    with traced("demo.replay"):
        pass
    summary = get_recorder().summarize()
    print(f"per-span summary from this run: {summary}")


def main() -> None:
    profile = milestone_1_structured_intake()
    milestone_2_single_agent()
    milestone_3_memory(profile)
    milestone_4_rag()
    milestone_5_graph(profile)
    milestone_6_team()
    milestone_7_observability()
    banner("Done - every milestone ran offline, no API key required.")


if __name__ == "__main__":
    main()
