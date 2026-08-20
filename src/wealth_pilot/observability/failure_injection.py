"""Milestone 7: failure injection.

You cannot know the retry/circuit-breaker harness actually works until
you have watched it survive a failure you caused on purpose. These
decorators inject deterministic or randomized failures into an otherwise
working call, for use in tests that assert the harness recovers.
"""

from __future__ import annotations

import functools
import random
import time
from typing import Callable, TypeVar

from wealth_pilot.agent.harness import TransientError

T = TypeVar("T")


def flaky(failure_rate: float, *, rng: random.Random | None = None) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Wraps a function so it raises TransientError with the given
    probability instead of running — for exercising retry_with_backoff.
    """

    rng = rng or random.Random()

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> T:
            if rng.random() < failure_rate:
                raise TransientError(f"injected failure in {fn.__name__}")
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def fail_n_times(n: int) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Fails the first n calls, then succeeds — for testing that a capped
    retry loop recovers within its budget but not beyond it.
    """

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        state = {"calls": 0}

        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> T:
            state["calls"] += 1
            if state["calls"] <= n:
                raise TransientError(f"injected failure {state['calls']}/{n} in {fn.__name__}")
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def inject_latency(seconds: float, *, sleep: Callable[[float], None] = time.sleep) -> Callable[[Callable[..., T]], Callable[..., T]]:
    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> T:
            sleep(seconds)
            return fn(*args, **kwargs)

        return wrapper

    return decorator
