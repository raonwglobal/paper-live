# paper-live

Agent·Skill 기반 **페이퍼 / 가상 / 라이브 가능 퀀트 실행 런타임**입니다.

paper-live는 선택적 **고기능 실행 백엔드**입니다. 환경 격리, 리스크, 승인, 가상 매칭, 브로커 라우팅, 암호화 시크릿 저장을 담당하며, 외부 MCP Gateway가 아닙니다. 호출자(CLI, 에이전트, 외부 게이트웨이)는 프로세스 내 `InternalTradeFacade`를 사용합니다.

## 주요 기능

- **환경**: `PAPER_SANDBOX` / `VIRTUAL_BACKTEST` / `REAL_LIVE` (HMAC 승격)
- **Paper 실행**: `PaperOrderRequest` + `VirtualMatchingEngine` + fail-closed `ExecutionGateway`
- **Live 브로커**: `BrokerOrderRequest` + `BrokerRouter` + Toss/KB
- **리스크**: `RiskGuardian` (노셔널·포지션·일손실·서킷브레이커)
- **승인**: 환경 승격 게이트와 주문 TTL/`approval_id` 게이트 분리
- **거래 API**: `OrderIntent` → `preview` → `submit` (`trade_facade.py`)
- **시크릿**: `SecretBroker` + Drive AES-GCM 스토어 (`GoogleDriveSecretStore`)
- **데이터**: `GoogleDriveStorageAgent` (버전 JSONL + manifest)

## 안전 원칙

- 기본 모드는 **PAPER_SANDBOX**
- **REAL_LIVE**는 자동 활성화되지 않음
- Live **submit**은 `approval_id` 필수, 자격 증명은 **SecretBroker**로만 resolve (응답에 미포함)
- Paper gateway는 REAL_LIVE에서 실행 거부
- API 키를 소스에 두지 말 것 (env + Drive 암호문)

## 빠른 시작

```bash
python -m pip install -e '.[test]'
pytest -q
```

상세 코드 예와 Google Drive 환경 변수는 [README.md](README.md)를 참고하세요.

### Google Drive 요약

| 용도 | 모듈 | 주요 env |
|------|------|----------|
| API 키 (암호문) | `secrets.GoogleDriveSecretStore` | `GOOGLE_DRIVE_ACCESS_TOKEN`, `GOOGLE_DRIVE_SECRET_KEY` |
| 시장 데이터 아카이브 | `data_lake.GoogleDriveStorageAgent` | `GOOGLE_DRIVE_DATA_ACCESS_TOKEN` |

Drive에는 시크릿 **평문이 저장되지 않습니다**. 암호화 키는 호스트 env에만 둡니다.

## 구조

```text
src/paper_live/
  trade_facade.py   # Intent / Preview / Submit
  secrets/          # SecretBroker, Drive 암호화 스토어
  data_lake.py      # 데이터셋 아카이브
  environment.py execution.py risk.py brokers/ ...
```

## 내부 HTTP API (P1)

| Method | Path | 인증 |
|--------|------|------|
| GET | `/internal/health` | `X-Internal-Token` |
| POST | `/internal/trade/preview` | `X-Internal-Token` |
| POST | `/internal/trade/submit` | `X-Internal-Token` |

`create_internal_server` / `serve_internal_api` 로 기동합니다. 응답에 API 키·토큰은 포함되지 않습니다. 상세는 [README.md](README.md) 참고.

AI 에이전트는 리포지토리 작업 시 `AGENTS.md`를 먼저 읽으세요.
