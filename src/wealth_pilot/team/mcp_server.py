"""Milestone 6: MCP integration.

MCP standardizes how an agent uses a capability — "the agent's hands" —
through a defined transport and JSON-RPC messages for discovery and tool
calls. Exposing `get_market_data` here means any MCP-conformant agent,
not just this project's own team, can reach it without a bespoke
integration. Requires the optional `mcp` extra: `pip install -e ".[mcp]"`.

Run directly to serve over stdio:
    python -m wealth_pilot.team.mcp_server
"""

from mcp.server.fastmcp import FastMCP

from wealth_pilot.agent.tools import get_portfolio, get_quote

mcp = FastMCP("wealth-pilot-market-data")


@mcp.tool()
def get_market_data(symbol: str) -> dict:
    """Get the current price for a market symbol (e.g. NIFTY50, VOO, GOLD_ETF).
    Use for a CURRENT price only. Do NOT use for historical prices or forecasts.
    """

    return get_quote(symbol)


@mcp.tool()
def get_client_portfolio(client_id: str) -> dict:
    """Get a client's current holdings as percentages. Read-only."""

    return get_portfolio(client_id)


if __name__ == "__main__":
    mcp.run()
