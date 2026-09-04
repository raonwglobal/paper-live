# Trading Pipeline

The paper runtime now connects analysis, debate, risk, execution and reflection.

```text
Market Input
  -> TradingGraph
  -> Macro/Fundamental/Technical/Sentiment
  -> Debate
  -> RiskGuardian
  -> ExecutionGateway
  -> VirtualMatchingEngine
  -> EpisodicMemory/SelfReflection
```

The default environment remains `PAPER_SANDBOX`. Live broker access is not implicitly enabled by this pipeline.

Lifecycle states are explicit: `INGESTED -> ANALYZED -> DEBATED -> RISK_APPROVED -> EXECUTED -> REFLECTED`, with rejection paths terminating in reflection.
