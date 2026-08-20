# Wealth Pilot

An agentic AI wealth-advisory pilot, built as seven milestones from a
four-day agentic-AI engineering course (IIT Hyderabad · AI LaunchPad).
Each milestone below is a runnable, tested piece of the same system: a
Portfolio Analyst agent, a memory layer, a RAG pipeline over fund fact
sheets and policy documents, a checkpointed planning workflow with
human-in-the-loop approval, and a supervised multi-agent compliance team.

Everything runs **offline by default** — a deterministic mock LLM provider
means `pytest` and the demo script need no API key and make no network
calls. Real providers (OpenAI / Anthropic / Groq) are a one-line env-var
swap away.

```bash
python examples/demo.py
```

## Milestones

| # | Milestone | Course origin | Code |
|---|---|---|---|
| 1 | Provider-agnostic LLM client + structured intake | Day 1, Session 1 | [`llm/`](src/wealth_pilot/llm) |
| 2 | Tool-enabled single agent (capped ReAct loop, harnessed) | Day 1, Session 2 | [`agent/`](src/wealth_pilot/agent) |
| 3 | Persistent memory + semantic index | Day 2, Session 1 | [`memory/`](src/wealth_pilot/memory) |
| 4 | Production RAG + evaluation baseline | Day 2, Session 2 | [`rag/`](src/wealth_pilot/rag) |
| 5 | Orchestrated LangGraph workflow with checkpointing | Day 3, Session 1 | [`graph/`](src/wealth_pilot/graph) |
| 6 | Specialized multi-agent team + MCP integration | Day 3, Session 2 | [`team/`](src/wealth_pilot/team) |
| 7 | Observability & failure injection (production hardening) | Day 4 | [`observability/`](src/wealth_pilot/observability) |

### 1 — Provider-agnostic LLM client + structured intake
`LLMClient` manages the message list so call sites never resend history by
hand, and swaps between a mock/OpenAI/Anthropic/Groq provider behind one
call shape. `generate_structured()` is the self-repair loop: generate,
validate against a Pydantic schema (`FinancialProfile`), and on failure
feed the *exact* validation error back to the model — capped at a few
attempts, after which it raises `EscalateToHuman` instead of looping
forever.

### 2 — Tool-enabled single agent
`PortfolioAnalystAgent` runs a capped Thought → Action → Observation loop
over five tools (`get_quote`, `get_portfolio`, `calculate_risk_metrics`,
`convert_currency`, `simulate_rebalance`). The one mutating tool
(`simulate_rebalance`) refuses to run without an idempotency key. Every
tool call goes through a retry-with-backoff + circuit-breaker harness
(`agent/harness.py`) so a flaky dependency degrades gracefully instead of
crashing the agent.

### 3 — Persistent memory + semantic index
`MemoryStore` keeps CoALA's four memory kinds genuinely distinct: working
(in-process, never persisted), episodic (timestamped JSONL), semantic
(deduped facts with confidence), and procedural (reusable strategies).
`consolidate()` is the "Dreaming" batch job — it prunes expired facts and
merges near-duplicates by embedding similarity, without touching another
client's memory. Embeddings are a small local, deterministic function
(`memory/embeddings.py`) so semantic search needs no external API.

### 4 — Production RAG + evaluation baseline
`rag/chunking.py` implements fixed-size, recursive, and Markdown-structure
chunking. `HybridIndex` fuses BM25 (exact fund codes, policy IDs) and
dense search via Reciprocal Rank Fusion, then `rerank()` re-scores the
fused candidates. `rag/security.py` treats every retrieved chunk as
untrusted: `data/fund_fact_sheets/vendor_proposal_flagged.md` contains a
deliberately hidden prompt injection that `scan()` catches across all five
of the course's injection categories, and `sanitize_for_context()`
delimits retrieved text before it reaches a prompt. `rag/evaluate.py`
scores retrieval against `data/golden_set.json` (Recall@K, Precision@K,
MRR@K) — the discipline of proving a pipeline is better, not eyeballing it.

### 5 — Orchestrated LangGraph workflow with checkpointing
`graph/workflow.py` is `risk_profile → draft_plan → execute_plan`, compiled
with a SQLite checkpointer and `interrupt_before=["execute_plan"]` — no
investment plan executes without an explicit human decision. A rejected
plan loops back to `draft_plan` up to `MAX_REVISIONS` times before
escalating to a human. Because state is checkpointed at every step, a
*new* graph instance pointed at the same SQLite file resumes an
in-progress plan exactly where a "crashed" process left off — see
`test_crash_recovery_resumes_from_last_checkpoint_with_a_fresh_process`.

### 6 — Specialized multi-agent team + MCP integration
A supervisor routes between four scoped specialists — Research Analyst,
Risk Assessor, Portfolio Strategist, Compliance Reviewer — each of which
can only write its own state keys (enforced by the `@scoped` decorator).
The Compliance Reviewer can reject a proposal and send it back to the
Strategist, capped at `MAX_REVISIONS` before escalating to a human rather
than looping "until it's good." `team/mcp_server.py` exposes the same
market-data tools over MCP (`pip install -e ".[mcp]"` then
`python -m wealth_pilot.team.mcp_server`) so any MCP-conformant agent can
reach them without a bespoke integration.

### 7 — Observability & failure injection (production hardening)
`traced()` always records a span locally — duration, inputs, outputs,
errors — and additionally forwards to LangFuse when
`LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` are set, never raising if
they're not. `SpanRecorder.summarize()` builds a per-operation
cost/latency table straight from what was traced. `observability/failure_injection.py`
provides `flaky()` and `fail_n_times()` decorators used in the test suite
to prove the retry/circuit-breaker harness from Milestone 2 actually
recovers from — and correctly gives up on — injected failures.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"
pytest                      # 46 tests, fully offline
python examples/demo.py     # walks through all 7 milestones end to end
```

To use a real model instead of the offline mock, copy `.env.example` to
`.env` and fill in one provider:

```bash
cp .env.example .env
# then set LLM_PROVIDER=openai (or anthropic / groq) and the matching *_API_KEY
```

## Project layout

```
src/wealth_pilot/
  llm/            Milestone 1 — client, schemas, self-repair loop
  agent/          Milestone 2 — tools, harness, single agent
  memory/         Milestone 3 — store, embeddings, consolidation
  rag/            Milestone 4 — chunking, hybrid index, rerank, security, eval
  graph/          Milestone 5 — LangGraph state + checkpointed workflow
  team/           Milestone 6 — specialist agents, supervisor, MCP server
  observability/  Milestone 7 — tracing, failure injection
data/
  fund_fact_sheets/   sample fund/policy documents used by the RAG demo
  golden_set.json     retrieval evaluation set
examples/demo.py       end-to-end walkthrough, offline
tests/                  46 tests, one file per milestone
```

## A note on secrets

`.env` is git-ignored. `.env.example` ships with every value blank. If
you're bringing over API keys from course material (LangFuse, Groq, etc.),
paste them into your own local `.env` only — never into a file that gets
committed.

## License

MIT — see [LICENSE](LICENSE).
