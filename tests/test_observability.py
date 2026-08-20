import pytest

from wealth_pilot.agent.harness import CircuitBreaker, TransientError, retry_with_backoff
from wealth_pilot.observability.failure_injection import fail_n_times, flaky
from wealth_pilot.observability.tracing import get_recorder, reset_recorder, traced


def test_traced_records_a_span_with_duration():
    reset_recorder()
    with traced("test.op", x=1) as out:
        out["result"] = 42
    spans = get_recorder().spans
    assert len(spans) == 1
    assert spans[0].name == "test.op"
    assert spans[0].outputs == 42
    assert spans[0].duration_ms >= 0


def test_traced_records_errors_without_swallowing_the_exception():
    reset_recorder()
    with pytest.raises(ValueError):
        with traced("test.failing_op"):
            raise ValueError("boom")
    spans = get_recorder().spans
    assert spans[-1].error == "boom"


def test_summary_aggregates_by_span_name():
    reset_recorder()
    for _ in range(3):
        with traced("agent.tool_call") as out:
            out["result"] = "ok"
    summary = get_recorder().summarize()
    assert summary["agent.tool_call"]["count"] == 3


def test_retry_with_backoff_recovers_within_budget():
    @retry_with_backoff(max_attempts=3, base_delay=0, sleep=lambda _s: None)
    @fail_n_times(2)
    def sometimes_fails() -> str:
        return "ok"

    assert sometimes_fails() == "ok"


def test_retry_with_backoff_gives_up_beyond_budget():
    @retry_with_backoff(max_attempts=2, base_delay=0, sleep=lambda _s: None)
    @fail_n_times(5)
    def always_fails_within_budget() -> str:
        return "ok"

    with pytest.raises(TransientError):
        always_fails_within_budget()


def test_circuit_breaker_opens_after_threshold_and_blocks_further_calls():
    breaker = CircuitBreaker(failure_threshold=2, cooldown_seconds=999)

    def failing():
        raise TransientError("down")

    for _ in range(2):
        with pytest.raises(TransientError):
            breaker.call(failing)

    with pytest.raises(RuntimeError, match="circuit open"):
        breaker.call(lambda: "would have worked")


def test_flaky_decorator_is_probabilistic_but_deterministic_with_a_seeded_rng():
    import random

    rng = random.Random(42)

    @flaky(0.5, rng=rng)
    def op() -> str:
        return "ok"

    outcomes = []
    for _ in range(10):
        try:
            outcomes.append(op())
        except TransientError:
            outcomes.append("failed")
    assert "ok" in outcomes and "failed" in outcomes
