"""Milestone 2: tools the Portfolio Analyst agent can ask the app to run.

The model never executes anything — it only ever produces the equivalent
of "I would like to call X with these arguments"; `ToolRegistry.invoke`
is the application code that decides whether to comply. Every tool name
is verb-first and unambiguous; every description states both what the
tool does and what it does not do.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

# --- deterministic, offline "market data" so the agent is testable without a live feed ---
_MOCK_QUOTES = {
    "NIFTY50": 24_850.30,
    "SENSEX": 81_200.10,
    "VOO": 512.44,
    "GOLD_ETF": 71.20,
}

_MOCK_PORTFOLIOS = {
    "client-001": {"NIFTY50": 40, "GOLD_ETF": 10, "VOO": 30, "CASH": 20},
}

_FX_RATES = {("USD", "INR"): 87.5, ("INR", "USD"): 1 / 87.5, ("EUR", "INR"): 94.8, ("INR", "EUR"): 1 / 94.8}

# idempotency ledger: idempotency_key -> result already produced
_REBALANCE_LEDGER: dict[str, dict[str, Any]] = {}


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    func: Callable[..., Any]
    idempotent: bool = True  # False => a mutating action; caller MUST supply idempotency_key
    required_args: tuple[str, ...] = field(default_factory=tuple)

    def to_schema(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "parameters": self.parameters}


def get_quote(symbol: str) -> dict[str, Any]:
    if symbol not in _MOCK_QUOTES:
        raise KeyError(f"Unknown symbol: {symbol}")
    return {"symbol": symbol, "price": _MOCK_QUOTES[symbol], "currency": "INR"}


def get_portfolio(client_id: str) -> dict[str, Any]:
    if client_id not in _MOCK_PORTFOLIOS:
        raise KeyError(f"Unknown client_id: {client_id}")
    return {"client_id": client_id, "holdings_pct": _MOCK_PORTFOLIOS[client_id]}


def calculate_risk_metrics(holdings_pct: dict[str, int]) -> dict[str, Any]:
    equity_like = {"NIFTY50", "SENSEX", "VOO"}
    equity_pct = sum(v for k, v in holdings_pct.items() if k in equity_like)
    # a simple, transparent heuristic — not a real risk model
    volatility_score = round(equity_pct * 0.18, 2)
    return {"equity_allocation_pct": equity_pct, "volatility_score": volatility_score}


def convert_currency(amount: float, from_currency: str, to_currency: str) -> dict[str, Any]:
    if from_currency == to_currency:
        rate = 1.0
    else:
        key = (from_currency, to_currency)
        if key not in _FX_RATES:
            raise KeyError(f"No FX rate for {from_currency}->{to_currency}")
        rate = _FX_RATES[key]
    return {"amount": round(amount * rate, 2), "currency": to_currency}


def simulate_rebalance(client_id: str, target_allocation_pct: dict[str, int], idempotency_key: str) -> dict[str, Any]:
    """Mutating: writes a new target allocation. Safe to call twice by accident —
    a repeated idempotency_key returns the original result instead of rebalancing again.
    """

    if idempotency_key in _REBALANCE_LEDGER:
        cached = dict(_REBALANCE_LEDGER[idempotency_key])
        cached["replayed"] = True
        return cached
    total = sum(target_allocation_pct.values())
    if total != 100:
        raise ValueError(f"target_allocation_pct must sum to 100, got {total}")
    _MOCK_PORTFOLIOS[client_id] = dict(target_allocation_pct)
    result = {"client_id": client_id, "new_allocation_pct": target_allocation_pct, "replayed": False}
    _REBALANCE_LEDGER[idempotency_key] = result
    return result


TOOLS: list[Tool] = [
    Tool(
        name="get_quote",
        description=(
            "Get the current price for a market symbol (e.g. NIFTY50, VOO). "
            "Use for a CURRENT price only. Do NOT use for historical prices or forecasts."
        ),
        parameters={
            "type": "object",
            "properties": {"symbol": {"type": "string", "enum": list(_MOCK_QUOTES)}},
            "required": ["symbol"],
        },
        func=get_quote,
        idempotent=True,
        required_args=("symbol",),
    ),
    Tool(
        name="get_portfolio",
        description="Get a client's current holdings as percentages. Read-only.",
        parameters={
            "type": "object",
            "properties": {"client_id": {"type": "string"}},
            "required": ["client_id"],
        },
        func=get_portfolio,
        idempotent=True,
        required_args=("client_id",),
    ),
    Tool(
        name="calculate_risk_metrics",
        description=(
            "Compute a volatility score from a holdings-percentage dict. "
            "Pure calculation, no side effects. Does NOT fetch live data itself."
        ),
        parameters={
            "type": "object",
            "properties": {"holdings_pct": {"type": "object"}},
            "required": ["holdings_pct"],
        },
        func=calculate_risk_metrics,
        idempotent=True,
        required_args=("holdings_pct",),
    ),
    Tool(
        name="convert_currency",
        description="Convert an amount between two supported currencies at a fixed reference rate.",
        parameters={
            "type": "object",
            "properties": {
                "amount": {"type": "number"},
                "from_currency": {"type": "string"},
                "to_currency": {"type": "string"},
            },
            "required": ["amount", "from_currency", "to_currency"],
        },
        func=convert_currency,
        idempotent=True,
        required_args=("amount", "from_currency", "to_currency"),
    ),
    Tool(
        name="simulate_rebalance",
        description=(
            "Write a new target allocation for a client (simulated, no real money moves). "
            "NOT safe to call twice without the same idempotency_key — a repeat call with a "
            "new key would rebalance again."
        ),
        parameters={
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "target_allocation_pct": {"type": "object"},
                "idempotency_key": {"type": "string"},
            },
            "required": ["client_id", "target_allocation_pct", "idempotency_key"],
        },
        func=simulate_rebalance,
        idempotent=False,
        required_args=("client_id", "target_allocation_pct", "idempotency_key"),
    ),
]


class ToolRegistry:
    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools = {t.name: t for t in (tools if tools is not None else TOOLS)}

    def schemas(self) -> list[dict[str, Any]]:
        return [t.to_schema() for t in self._tools.values()]

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")
        return self._tools[name]

    def invoke(self, name: str, arguments: dict[str, Any]) -> Any:
        tool = self.get(name)
        if not tool.idempotent and "idempotency_key" not in arguments:
            raise ValueError(f"Tool {name!r} is not idempotent and requires an idempotency_key")
        missing = [a for a in tool.required_args if a not in arguments]
        if missing:
            raise ValueError(f"Tool {name!r} missing required arguments: {missing}")
        return tool.func(**arguments)
