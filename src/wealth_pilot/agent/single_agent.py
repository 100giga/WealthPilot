"""Milestone 2: a tool-enabled single agent running a capped ReAct loop.

Thought, Action, Observation, repeat — the model reasons about what to do
next, calls a tool, observes the result, and continues until it decides
the task is complete or the iteration cap is hit. The cap exists because
the model will not stop itself; the harness sets the limit.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from wealth_pilot.agent.harness import (
    CircuitBreaker,
    TransientError,
    get_logger,
    log_event,
    retry_with_backoff,
)
from wealth_pilot.agent.tools import ToolRegistry
from wealth_pilot.llm.client import LLMClient

SYSTEM_PROMPT = """You are a Portfolio Analyst agent for a wealth-management pilot.
You may use these tools: {tool_schemas}

On every turn, respond with ONLY one JSON object, no prose, no markdown fences:
  - to call a tool:   {{"thought": "...", "action": {{"tool": "<name>", "arguments": {{...}}}}}}
  - to finish:        {{"thought": "...", "final_answer": "..."}}

Never invent a tool result. Call a tool if you need data you don't already have."""


class AgentIterationLimitExceeded(Exception):
    pass


def _extract_json(text: str) -> dict[str, Any]:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    raw = fenced.group(1) if fenced else text
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    return json.loads(match.group(0) if match else raw)


@dataclass
class AgentStep:
    thought: str
    action: dict[str, Any] | None
    observation: Any = None
    final_answer: str | None = None


@dataclass
class PortfolioAnalystAgent:
    client: LLMClient
    registry: ToolRegistry = field(default_factory=ToolRegistry)
    max_iterations: int = 6
    circuit_breaker: CircuitBreaker = field(default_factory=CircuitBreaker)

    def __post_init__(self) -> None:
        self._logger = get_logger()
        if not any(m["role"] == "system" for m in self.client.messages):
            self.client.messages.insert(
                0,
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT.format(tool_schemas=json.dumps(self.registry.schemas())),
                },
            )

    def _invoke_tool_safely(self, name: str, arguments: dict[str, Any]) -> Any:
        @retry_with_backoff(max_attempts=3, base_delay=0.01, sleep=lambda _s: None)
        def call() -> Any:
            try:
                return self.registry.invoke(name, arguments)
            except (KeyError, ValueError):
                raise  # not transient — a bad call won't fix itself by retrying
            except Exception as exc:  # pragma: no cover - defensive
                raise TransientError(str(exc)) from exc

        return self.circuit_breaker.call(call)

    def run(self, task: str) -> tuple[str, list[AgentStep]]:
        steps: list[AgentStep] = []
        message = task
        for iteration in range(1, self.max_iterations + 1):
            raw = self.client.chat(message)
            try:
                parsed = _extract_json(raw)
            except json.JSONDecodeError:
                message = "That was not valid JSON. Respond with ONLY the JSON object described earlier."
                log_event(self._logger, "agent.parse_error", iteration=iteration)
                continue

            thought = parsed.get("thought", "")
            if "final_answer" in parsed:
                step = AgentStep(thought=thought, action=None, final_answer=parsed["final_answer"])
                steps.append(step)
                log_event(self._logger, "agent.final_answer", iteration=iteration)
                return parsed["final_answer"], steps

            action = parsed.get("action")
            if not action:
                message = 'Respond with either "action" or "final_answer".'
                continue

            tool_name, tool_args = action.get("tool"), action.get("arguments", {})
            log_event(self._logger, "agent.tool_call", iteration=iteration, tool=tool_name, arguments=tool_args)
            try:
                observation = self._invoke_tool_safely(tool_name, tool_args)
                message = f"Observation: {json.dumps(observation, default=str)}"
            except Exception as exc:
                observation = {"error": str(exc)}
                message = f"Observation: tool call failed with error: {exc}"
            steps.append(AgentStep(thought=thought, action=action, observation=observation))

        raise AgentIterationLimitExceeded(
            f"No final_answer after {self.max_iterations} iterations — escalate to a human."
        )
