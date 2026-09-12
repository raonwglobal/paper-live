# System Test Plan

## Objective

Verify that the Agent/Skill runtime cannot cross execution environments and that Paper Trading remains deterministic and safe.

## Isolation tests

1. `PAPER_SANDBOX` + Toss skill => reject.
2. `PAPER_SANDBOX` + KB skill => reject.
3. `PAPER_SANDBOX` + Virtual Matching => allow.
4. `VIRTUAL_BACKTEST` + Live broker => reject.
5. `REAL_LIVE` without valid authorization => reject.
6. Unknown mode => reject.
7. Invalid mode transition => state unchanged.

## Risk tests

- position limit exceeded => reject
- daily loss limit exceeded => reject
- circuit breaker active => reject
- kill switch active => reject
- distributed lock failure => fail closed

## Execution tests

- market order
- limit order
- partial fill
- cancel/replace
- insufficient virtual cash
- insufficient virtual position
- duplicate client order ID
- deterministic replay

## Failure tests

- LLM timeout => Rule-Based fallback
- market data timeout => no new order
- broker timeout => conservative handling and alert
- Redis unavailable => fail closed for protected operations

## Security tests

- live secret absent from Paper process
- logs do not expose secrets
- mode transition requires authorization
- skill allow-list cannot be overridden by model output

## Release gate

No Paper release is considered complete unless all isolation tests pass and no test demonstrates a path from `PAPER_SANDBOX` to a live broker skill.
