# Agent & Skill Runtime Architecture

## Runtime flow

`Market Ingest -> Analysis Agents -> Debate -> Risk Gate -> Execution -> Ledger -> Reflection`

## Hard isolation rule

ExecutionTraderAgent never selects a broker directly from arbitrary model output. It receives the authoritative `ExecutionEnvironmentMode` from Environment Controller and resolves an allow-list.

- `PAPER_SANDBOX`: only `skill-virtual-matching-engine`
- `VIRTUAL_BACKTEST`: only virtual/backtest execution
- `REAL_LIVE`: only explicitly enabled broker adapter (`Toss`/`KB`)

A mode mismatch is a hard denial, not a retry.

## Contracts

Agents emit typed analysis and order-intent objects. Skills accept validated inputs and return deterministic typed results. LLM-generated free-form strings are never passed directly to a broker adapter.

## Event boundaries

Core events:

- `market.snapshot.received`
- `analysis.completed`
- `debate.completed`
- `risk.approved`
- `risk.rejected`
- `order.submitted`
- `order.partially_filled`
- `order.filled`
- `order.cancelled`
- `execution.failed`
- `reflection.completed`

Each event carries `event_id`, `correlation_id`, timestamp, execution mode and actor/skill identity.
