# Priority Completion Plan

The project will complete these five gates before PR approval/merge:

1. **Real P&L and Portfolio Lifecycle** — connect fills, positions, realized/unrealized P&L and reflection records.
2. **Order Lifecycle / Idempotency** — deterministic NEW/PARTIALLY_FILLED/FILLED/CANCELED/REJECTED state transitions and duplicate-request protection.
3. **Live Approval and Environment Isolation** — make LiveApprovalGate a mandatory boundary for REAL_LIVE and keep Paper/Backtest fail-closed.
4. **Production LangGraph + Agent/Skill Runtime** — replace or explicitly adapt the dependency-free graph with a real LangGraph StateGraph while preserving deterministic skill boundaries.
5. **Data Skills + E2E/Failure Tests** — implement production data adapters and exercise isolation, broker, risk, network, lock, LLM, duplicate-order and partial-fill failure paths.

A gate is complete only when implementation, unit/integration tests, and CI evidence are present. Passing unit tests alone does not mark a gate complete.
