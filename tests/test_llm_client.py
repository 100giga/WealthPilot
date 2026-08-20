import pytest
from pydantic import BaseModel, Field

from wealth_pilot.llm.client import LLMClient, MockProvider, estimate_daily_cost
from wealth_pilot.llm.repair import EscalateToHuman, generate_structured
from wealth_pilot.llm.schemas import FinancialProfile


def test_client_manages_message_history_across_turns():
    client = LLMClient(provider=MockProvider(), system_prompt="You are a test bot.")
    client.chat("hello")
    client.chat("again")
    roles = [m["role"] for m in client.messages]
    assert roles == ["system", "user", "assistant", "user", "assistant"]


def test_reset_keeps_only_system_prompt():
    client = LLMClient(provider=MockProvider(), system_prompt="sys")
    client.chat("hi")
    client.reset()
    assert [m["role"] for m in client.messages] == ["system"]


def test_estimate_daily_cost_matches_worked_example():
    # 200 tokens/turn, 20 turns/session, 500 sessions/day -> ~$5/day at a
    # representative per-million price used in the course's worked example.
    cost = estimate_daily_cost(200, 20, 500, price_per_million_tokens=2.5)
    assert cost == pytest.approx(5.0)


def test_structured_generation_succeeds_first_try():
    valid_json = FinancialProfile(
        full_name="Asha Rao", annual_income=1_200_000, monthly_expenses=40_000,
        current_savings=500_000, risk_tolerance="moderate", investment_horizon_years=10,
        primary_goal="retirement", currency="INR",
    ).model_dump_json()
    client = LLMClient(provider=MockProvider(script=[valid_json]))
    profile = generate_structured(client, "Extract the profile.", FinancialProfile)
    assert profile.full_name == "Asha Rao"


def test_self_repair_loop_recovers_from_bad_json():
    malformed = '{"full_name": "Asha Rao", "annual_income": "around 12 lakh"}'
    fixed = FinancialProfile(
        full_name="Asha Rao", annual_income=1_200_000, monthly_expenses=40_000,
        current_savings=500_000, risk_tolerance="moderate", investment_horizon_years=10,
        primary_goal="retirement", currency="INR",
    ).model_dump_json()
    client = LLMClient(provider=MockProvider(script=[malformed, fixed]))
    profile = generate_structured(client, "Extract the profile.", FinancialProfile, max_attempts=3)
    assert profile.annual_income == 1_200_000
    # 2 user+assistant pairs means the repair loop actually round-tripped the error once
    assert len(client.messages) == 4
    assert client.provider.call_count == 2


def test_self_repair_loop_escalates_after_cap():
    always_bad = '{"full_name": "X"}'  # missing required fields, forever
    client = LLMClient(provider=MockProvider(script=[always_bad, always_bad, always_bad]))
    with pytest.raises(EscalateToHuman):
        generate_structured(client, "Extract the profile.", FinancialProfile, max_attempts=3)
    assert client.provider.call_count == 3


def test_shape_valid_but_semantically_wrong_output_is_rejected():
    # {"total": -450.00, ...}-style trap: valid JSON, invalid business rule.
    with pytest.raises(Exception):
        FinancialProfile(
            full_name="X", annual_income=-450.0, monthly_expenses=0, current_savings=0,
            risk_tolerance="moderate", investment_horizon_years=5, primary_goal="x", currency="XYZ",
        )
