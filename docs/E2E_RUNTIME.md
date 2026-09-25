# E2E Runtime

The paper runtime executes one deterministic cycle:

1. Market snapshot enters `PaperTradingCycle`.
2. Macro, Fundamental, Technical and Sentiment agents populate `AgentState`.
3. `DebateOrchestratorAgent` produces BUY/SELL/HOLD.
4. `RiskGuardian` performs deterministic pre-trade checks.
5. `ExecutionGateway` enforces `EnvironmentController` skill isolation.
6. `VirtualMatchingEngine` executes PAPER_SANDBOX orders.
7. Portfolio cash and positions are updated.

`REAL_LIVE` is never reachable through the paper gateway. Live broker adapters remain a separate explicitly authorized path.
