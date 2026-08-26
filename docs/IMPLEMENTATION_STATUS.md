# Implementation Status

## Implemented

- W1 Environment Controller and execution modes
- W2 Skill allow-list / fail-closed execution gateway
- W3 Paper matching engine with fee, tax, slippage and partial fills
- Deterministic order lifecycle with idempotent client order IDs and cancellation
- Portfolio ledger with average cost, realized/unrealized/total P&L
- Risk Guardian and Circuit Breaker
- Technical SMA/EMA/RSI analytics
- Rule-based stock screener primitives
- Historical backtest runner and Sharpe / max-drawdown metrics
- LangGraph `StateGraph` agent orchestration for macro/fundamental/technical/sentiment/debate flow
- Episodic memory and self-reflection worker
- Append-only audit logger
- Time/KPI trigger evaluator with explicit live-approval requirement
- Mandatory `LiveApprovalGate` at `REAL_LIVE` environment promotion
- Environment-only broker credential loading
- Guarded Toss Securities Open API adapter
- Configurable KB Securities adapter boundary
- Deterministic macro/news data-skill contracts
- Priority live-isolation, risk, order-lifecycle and paper-failure-path tests
- Automated pytest GitHub Actions workflow

## Deliberately gated

- `REAL_LIVE` remains disabled unless deployment explicitly sets `PAPER_LIVE_ENABLE_LIVE=true`, supplies broker credentials, passes environment authorization, and has an explicit live approval.
- Toss adapter currently submits guarded LIMIT orders using the official documented `/v1/orders` contract.
- KB adapter requires the approved Fintech Store API product endpoint/payload mapping; the public login site does not expose those private contract details.

## Remaining project-level hardening

- Production persistent database/event store
- Distributed lock implementation (Redis/Redlock)
- Notification adapter
- Full external market-data connectors and production news/RAG/VLM providers
- Full live broker certification/test-bed validation
- Docker/observability/release packaging
- Expanded long-running end-to-end and failure-injection matrix

These are production-hardening items beyond the five priority completion gates. The five priority gates are considered implementation-complete only after their CI evidence and integration checks pass.
