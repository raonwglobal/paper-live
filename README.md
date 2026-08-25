# paper-live

Agent & Skill 기반 자율 퀀트 트레이딩 인프라의 안전한 Paper Trading 코어입니다.

## 현재 구현

- 기본 실행 모드: `PAPER_SANDBOX`
- `EnvironmentController` 구현
- `VirtualMatchingEngine` 구현
- `ExecutionGateway` fail-closed 실행 경계 구현
- `SkillRegistry` / environment allow-list 구현
- `RiskGuardian` / `CircuitBreaker` 구현
- Agent state/decision contracts 구현
- Toss / KB broker adapter boundary 구현
- 실제 Toss/KB 주문 API는 안전상 현재 비활성
- 단위 테스트 구현

## 실행

```bash
python -m pip install -e '.[test]'
pytest -q
```

## 안전 원칙

`REAL_LIVE`는 코드에 의해 자동 활성화되지 않습니다. Broker credential을 소스에 저장하지 않으며, 현재 broker adapter는 실제 주문을 거부합니다. Paper/Backtest에서는 virtual matching skill만 실행할 수 있습니다.

## 구조

```text
src/paper_live/
  environment.py  # execution mode + policy boundary
  execution.py    # paper matching + execution gateway
  risk.py         # deterministic risk gate
  skills.py       # skill registry
  agents.py       # agent contracts
  brokers.py      # broker adapter boundary
```

설계 문서는 `docs/` 아래에 있습니다.
