# [고도화] 에이전트 및 스킬 기반 자율 퀀트 트레이딩 시스템 프로젝트 수행 계획서

**Project Execution Plan: Agent & Skill-Based Autonomous Quantitative Trading Infrastructure**

- Version: v2.2
- Revised: 2026-08-25
- Primary execution mode: `PAPER_SANDBOX`
- Live trading: explicitly isolated and disabled by default

## 1. 프로젝트 개요

본 프로젝트는 자율형 멀티 에이전트와 모듈형 스킬 기반으로 토스증권 Open API 및 KB증권 핀테크스토어 연동을 준비하고, 실시간 시세 기반 Paper Trading과 지능형 자동화 퀀트 런타임을 구축한다.

핵심 원칙은 Agent(추론/의사결정)와 Skill(결정론적 데이터·실행 도구)의 분리다. 모든 주문 실행은 환경 모드와 Risk Gate를 통과해야 하며, `REAL_LIVE` 전환은 명시적 인증과 안전 스위칭 절차 없이는 허용하지 않는다.

## 2. 실행 환경 격리

| Mode | 시장 데이터 | 계좌 | 주문 실행 |
|---|---|---|---|
| `PAPER_SANDBOX` | 실시간/지연 데이터 | 가상 | `skill-virtual-matching-engine` |
| `VIRTUAL_BACKTEST` | 과거 데이터 | 가상 | 백테스트 매칭 |
| `REAL_LIVE` | 실시간 | 실제 | 승인된 Broker Skill |

환경 판정은 중앙 `skill-environment-controller`가 담당한다. 실행 에이전트가 환경을 우회하여 다른 Broker Skill을 호출하는 것을 구조적으로 금지한다.

## 3. 멀티 에이전트 StateGraph

1. `MacroRegimeAgent` — 거시 국면
2. `FundamentalAnalystAgent` — 공시/재무
3. `TechnicalVisionAgent` — OHLCV/차트
4. `SentimentQuantAgent` — 뉴스/시장심리
5. `DebateOrchestratorAgent` — Bull/Bear 토론 및 포지션 합성
6. `RiskGuardianAgent` — 3단계 위험 게이트 및 Circuit Breaker
7. `ExecutionTraderAgent` — 환경별 주문 실행
8. `Self-Reflection Worker` — 결과 평가 및 Episodic Memory 갱신

병렬 분석 결과는 합성 단계로 전달되고, 합성된 주문 의도는 Risk Gate를 거친 후에만 Execution 단계로 전달한다.

## 4. Skill Catalog

### Data & Analysis
- `skill-openbb-macro`
- `skill-financial-rag`
- `skill-sec-edgar-parser`
- `skill-chart-vlm`
- `skill-ta-indicators`
- `skill-news-sentiment-extractor`

### Broker & Execution
- `skill-toss-broker` — `REAL_LIVE` 전용
- `skill-kb-broker` — `REAL_LIVE` 전용
- `skill-virtual-matching-engine` — `PAPER_SANDBOX` / `VIRTUAL_BACKTEST` 전용
- `skill-risk-circuit-breaker`
- `skill-environment-controller`

## 5. Environment Controller

### API

```text
get_current_mode() -> ExecutionEnvironmentMode
set_mode(mode, auth_token) -> bool
register_time_trigger(target_time, mode) -> bool
register_kpi_trigger(metric, threshold, mode) -> bool
```

### 안전 정책

- 기본 모드는 `PAPER_SANDBOX`.
- `REAL_LIVE` 승격에는 인증 토큰과 별도 안전 검증이 필요하다.
- 전환 전 미체결 Paper 주문을 취소하거나 저장하는 정책을 명시한다.
- 실거래 자격 증명은 애플리케이션 코드에 저장하지 않는다.
- 모드 불일치 시 주문은 거부하고 감사 로그를 남긴다.

KPI Trigger는 자동 실거래 실행 권한으로 해석하지 않는다. KPI 충족은 **전환 후보 상태**를 만들 뿐이며 최종 실거래 승인은 별도의 명시적 승인 절차를 요구한다.

## 6. Risk Guardian

Risk Guardian은 주문 실행 전 최소 세 단계로 검증한다.

1. 전략/포트폴리오 한도
2. 주문/시장 미시구조 위험
3. Circuit Breaker / Kill Switch / 실행환경 일치성

LLM 장애 시 안전한 Rule-Based fallback으로 전환하고, 네트워크 장애나 락 획득 실패는 보수적인 주문 거부/롤백을 우선한다.

## 7. Virtual Matching Engine

Paper 환경에서는 실계좌 API를 호출하지 않는다. 가상 체결 엔진은 다음을 계산한다.

- 주문 유형 및 수량
- Bid/Ask 기반 체결
- 호가 깊이에 따른 슬리피지
- 수수료
- 거래세/제비용 정책
- 부분 체결
- 주문 상태 전이
- 잔고/포지션/평단 업데이트

모든 계산은 재현 가능한 deterministic engine으로 구현하고 테스트 가능하도록 인터페이스를 분리한다.

## 8. Self-Reflection 및 Memory

체결 이후 실제 주문 의도, 체결 결과, 당시 시장 상태, 손익 및 위험 지표를 기록한다. Reflection Worker는 결과를 분석하여 다음 실행에서 참고할 Episodic Memory를 갱신한다.

메모리 기록은 주문 원장과 분리하며, Reflection 결과가 직접 주문 권한을 상승시키지 않도록 한다.

## 9. 보안 원칙

- Broker secret은 환경변수/Secret Manager에서만 주입한다.
- Paper 환경에서는 Live credential을 런타임에 마운트하지 않는다.
- Broker Skill은 mode-aware authorization을 강제한다.
- 모든 주문 시도와 거부는 correlation ID와 함께 감사 로그로 남긴다.
- Kill Switch는 LLM과 독립된 deterministic control path로 제공한다.
- Redis lock을 사용하더라도 분산락 장애 시 fail-closed 정책을 적용한다.

## 10. WBS

### W1 — Environment Controller
- 모드 enum/state schema
- 상태 저장소
- mode transition API
- authorization gate

### W2 — Isolation & Safety
- Skill allow-list
- Paper/Live credential isolation
- transition rollback
- circuit breaker

### W3 — Virtual Matching
- order model
- matching engine
- fee/tax/slippage
- portfolio ledger

### W4 — Broker Abstraction
- Broker interface
- Toss adapter skeleton
- KB adapter skeleton
- routing policy

### W5 — Market/Data Skills
- macro
- fundamental
- technical
- sentiment

### W6 — Agent Runtime
- LangGraph StateGraph
- agent contracts
- tool/skill registry
- state/event schema

### W7 — Debate & Risk
- Bull/Bear debate
- position sizing
- Risk Guardian
- kill switch

### W8 — Reflection & Operations
- trade journal
- episodic memory
- alerting
- operational dashboards/logging

### W9 — System Test
- isolation ST
- order lifecycle ST
- failure/fallback ST
- replay/backtest ST
- security ST

### W10 — Release Hardening
- documentation
- configuration validation
- CI checks
- Paper production profile
- Live profile remains explicitly gated

## 11. 테스트 핵심 항목

| Test | Expected |
|---|---|
| Paper → Toss skill call | DENY |
| Paper → Virtual Matching | ALLOW |
| Backtest → Live broker | DENY |
| Live without valid auth | DENY |
| Risk limit exceeded | DENY |
| Kill switch active | DENY |
| Lock failure | FAIL-CLOSED |
| LLM unavailable | Rule-Based safe fallback |
| Partial fill | Ledger consistent |
| Duplicate order request | Idempotent handling |

## 12. 운영 원칙

Grok Project 또는 기타 자동화 런타임은 본 시스템의 분석/운영 보조 계층으로 사용할 수 있으나, Broker Credential과 직접 연결되는 실행 권한은 최소화한다. 자동화는 관측, 분석, 리포트, 알림부터 시작하고 실거래 권한은 별도 승인 경계 뒤에 둔다.

## 13. 범위 제외

- Payments/결제 시스템
- 실거래 자동 전환의 무조건적 실행
- LLM이 Risk Gate를 우회하는 구조
- Paper 모드에서 실제 Broker 주문 발주

## 14. 산출물

- 환경 제어 모듈
- Agent/Skill contract
- Broker abstraction 및 Toss/KB adapter
- Virtual Matching Engine
- Risk/Circuit Breaker
- LangGraph workflow
- 테스트 suite
- 보안/운영 문서
- Paper 실행 프로파일
