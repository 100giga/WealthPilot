import json

import pytest

from wealth_pilot.agent.single_agent import AgentIterationLimitExceeded, PortfolioAnalystAgent
from wealth_pilot.agent.tools import ToolRegistry
from wealth_pilot.llm.client import LLMClient, MockProvider


def _agent(script: list[str], max_iterations: int = 6) -> PortfolioAnalystAgent:
    client = LLMClient(provider=MockProvider(script=script))
    return PortfolioAnalystAgent(client=client, registry=ToolRegistry(), max_iterations=max_iterations)


def test_react_loop_calls_tool_then_answers():
    script = [
        json.dumps({"thought": "need a price", "action": {"tool": "get_quote", "arguments": {"symbol": "NIFTY50"}}}),
        json.dumps({"thought": "got it", "final_answer": "NIFTY50 is trading around 24,850."}),
    ]
    agent = _agent(script)
    answer, steps = agent.run("What's NIFTY50 trading at?")
    assert "24,850" in answer or "24850" in answer
    assert steps[0].action["tool"] == "get_quote"
    assert steps[0].observation["symbol"] == "NIFTY50"
    assert steps[-1].final_answer == answer


def test_agent_recovers_from_malformed_json_then_finishes():
    script = [
        "not json at all",
        json.dumps({"thought": "ok", "final_answer": "done"}),
    ]
    agent = _agent(script)
    answer, steps = agent.run("anything")
    assert answer == "done"


def test_agent_surfaces_tool_error_as_observation_not_a_crash():
    script = [
        json.dumps({"thought": "bad symbol", "action": {"tool": "get_quote", "arguments": {"symbol": "DOGE"}}}),
        json.dumps({"thought": "give up gracefully", "final_answer": "I couldn't find that symbol."}),
    ]
    agent = _agent(script)
    answer, steps = agent.run("price of DOGE?")
    assert "error" in steps[0].observation
    assert answer == "I couldn't find that symbol."


def test_mutating_tool_without_idempotency_key_is_rejected():
    script = [
        json.dumps(
            {
                "thought": "rebalance",
                "action": {
                    "tool": "simulate_rebalance",
                    "arguments": {"client_id": "client-001", "target_allocation_pct": {"NIFTY50": 100}},
                },
            }
        ),
        json.dumps({"thought": "noted", "final_answer": "could not rebalance safely"}),
    ]
    agent = _agent(script)
    _answer, steps = agent.run("rebalance to 100% equity")
    assert "idempotency_key" in steps[0].observation["error"]


def test_iteration_cap_is_enforced():
    script = [json.dumps({"thought": "thinking forever", "action": {"tool": "get_quote", "arguments": {"symbol": "NIFTY50"}}})]
    agent = _agent(script, max_iterations=2)
    with pytest.raises(AgentIterationLimitExceeded):
        agent.run("never finish")
