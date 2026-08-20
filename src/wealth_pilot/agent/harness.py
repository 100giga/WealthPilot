"""Milestone 2: the harness. Agent = Model + Harness — the loop, the tool
executor, retry and circuit-breaker logic, and logging are what make a tool
feel like a reliable coworker rather than an unpredictable chatbot.
"""

from __future__ import annotations

import functools
import json
import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def get_logger(name: str = "wealth_pilot") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    logger.info(json.dumps({"event": event, **fields}, default=str))


class TransientError(Exception):
    """Raised by callers to signal 'retry me' rather than 'give up'."""


def retry_with_backoff(
    *,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    jitter: float = 0.1,
    sleep: Callable[[float], None] = time.sleep,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """retry-with-backoff assumes a failure is transient and waits
    progressively longer between attempts (1s, then 2s, then 4s), with jitter.
    """

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exc: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except TransientError as exc:
                    last_exc = exc
                    if attempt == max_attempts:
                        break
                    delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, jitter)
                    sleep(delay)
            assert last_exc is not None
            raise last_exc

        return wrapper

    return decorator


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """A circuit breaker assumes a service is genuinely broken and stops
    calling it after a threshold of failures, testing again with a single
    call after a cooldown period.
    """

    failure_threshold: int = 3
    cooldown_seconds: float = 30.0
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _opened_at: float = field(default=0.0, init=False)
    _clock: Callable[[], float] = field(default=time.monotonic, init=False)

    @property
    def state(self) -> CircuitState:
        if self._state is CircuitState.OPEN and (self._clock() - self._opened_at) >= self.cooldown_seconds:
            self._state = CircuitState.HALF_OPEN
        return self._state

    def call(self, fn: Callable[[], T]) -> T:
        if self.state is CircuitState.OPEN:
            raise RuntimeError("circuit open — refusing call until cooldown elapses")
        try:
            result = fn()
        except Exception:
            self._failure_count += 1
            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = self._clock()
            raise
        else:
            self._failure_count = 0
            self._state = CircuitState.CLOSED
            return result
