"""Milestone 1: a provider-agnostic LLM client.

Every API call starts from zero — the model holds no state between calls.
`LLMClient` is the piece of application code that manages the message list
and lets the underlying provider be swapped without touching call sites.
Same shape, three different field names, three different response objects
per provider — this module is the layer that hides that.
"""

from __future__ import annotations

import abc
from typing import Protocol, TypedDict

from wealth_pilot.config import settings


class Message(TypedDict):
    role: str  # "system" | "user" | "assistant"
    content: str


class LLMProvider(Protocol):
    """The one method every provider must implement, whatever its native API looks like."""

    def complete(self, messages: list[Message], *, model: str, temperature: float = 0.2) -> str: ...


class MockProvider:
    """Deterministic, offline provider.

    With no `script`, replies with a plausible-sounding templated response —
    useful for the demo. With a `script`, pops one canned reply per call
    (repeating the last entry once exhausted) — used by tests to make
    self-repair loops, tool-call sequences and multi-turn flows reproducible
    without hitting a real API.
    """

    def __init__(self, script: list[str] | None = None) -> None:
        self._script = list(script) if script else None
        self._call_count = 0

    def complete(self, messages: list[Message], *, model: str, temperature: float = 0.2) -> str:
        self._call_count += 1
        if self._script:
            idx = min(self._call_count - 1, len(self._script) - 1)
            return self._script[idx]
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        return f"[mock:{model}] Acknowledged: {last_user[:120]}"

    @property
    def call_count(self) -> int:
        return self._call_count


class _HTTPProvider(abc.ABC):
    """Shared plumbing for real, API-key-backed providers."""

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError(f"{type(self).__name__} requires an API key")
        self._api_key = api_key

    @abc.abstractmethod
    def complete(self, messages: list[Message], *, model: str, temperature: float = 0.2) -> str: ...


class OpenAICompatibleProvider(_HTTPProvider):
    """Works for OpenAI, Groq and any other OpenAI-compatible chat/completions API."""

    def __init__(self, api_key: str, base_url: str) -> None:
        super().__init__(api_key)
        self._base_url = base_url.rstrip("/")

    def complete(self, messages: list[Message], *, model: str, temperature: float = 0.2) -> str:
        import httpx

        resp = httpx.post(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"model": model, "messages": messages, "temperature": temperature},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


class AnthropicProvider(_HTTPProvider):
    def complete(self, messages: list[Message], *, model: str, temperature: float = 0.2) -> str:
        import httpx

        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        turns = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "system": system,
                "messages": turns,
                "max_tokens": 1024,
                "temperature": temperature,
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]


def get_provider(name: str | None = None) -> LLMProvider:
    """Factory: same call shape regardless of which provider comes back."""

    name = (name or settings.llm_provider).lower()
    if name == "mock":
        return MockProvider()
    if name == "openai":
        return OpenAICompatibleProvider(settings.openai_api_key, "https://api.openai.com/v1")
    if name == "groq":
        return OpenAICompatibleProvider(settings.groq_api_key, "https://api.groq.com/openai/v1")
    if name == "anthropic":
        return AnthropicProvider(settings.anthropic_api_key)
    raise ValueError(f"Unknown LLM provider: {name!r}")


class LLMClient:
    """Manages the message list so call sites never resend history by hand,
    and swaps providers freely behind one call shape.
    """

    def __init__(
        self,
        provider: LLMProvider | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self.provider = provider or get_provider()
        self.model = model or settings.llm_model
        self.messages: list[Message] = []
        if system_prompt:
            self.messages.append({"role": "system", "content": system_prompt})

    def chat(self, user_message: str, *, temperature: float = 0.2) -> str:
        self.messages.append({"role": "user", "content": user_message})
        reply = self.provider.complete(self.messages, model=self.model, temperature=temperature)
        self.messages.append({"role": "assistant", "content": reply})
        return reply

    def reset(self) -> None:
        system = [m for m in self.messages if m["role"] == "system"]
        self.messages = system


def estimate_daily_cost(
    tokens_per_turn: int,
    turns_per_session: int,
    sessions_per_day: int,
    price_per_million_tokens: float,
) -> float:
    """tokens/day = tokens per turn x turns per session x sessions per day."""

    tokens_per_day = tokens_per_turn * turns_per_session * sessions_per_day
    return (tokens_per_day / 1_000_000) * price_per_million_tokens
