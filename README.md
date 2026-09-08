# paper-live

Agent & skill based **paper / virtual / live-capable quant execution runtime**.

paper-live is an optional high-capability **execution backend**: environment isolation, risk, approval, virtual matching, broker routing, and encrypted secret storage. It is not an external MCP gateway — callers (CLI, agents, or an external gateway) use the in-process `InternalTradeFacade` (HTTP internal API may be added later).

## Features

| Area | Module | Notes |
|------|--------|--------|
| Environment | `environment.py` | `PAPER_SANDBOX` / `VIRTUAL_BACKTEST` / `REAL_LIVE` + HMAC promotion |
| Paper execution | `execution.py` | `PaperOrderRequest`, `VirtualMatchingEngine`, `ExecutionGateway` (fail-closed on REAL_LIVE) |
| Live brokers | `brokers/` | `BrokerOrderRequest`, `BrokerRouter`, Toss/KB adapters |
| Risk | `risk.py` | `RiskGuardian`, circuit breaker, notional / position / daily loss |
| Approvals | `live_approval` + `security.live_approval_gate` | Env promotion vs per-order TTL/nonce |
| Trade API | `trade_facade.py` | `OrderIntent` → `preview` → `submit` |
| Secrets | `secrets/` | `SecretBroker` + `GoogleDriveSecretStore` (AES-GCM) / `InMemorySecretStore` |
| Market archive | `data_lake.py` | Versioned JSONL + manifest on Google Drive |
| Plugins / agents | `plugins/`, `agents.py` | Skill allow-list by environment |

## Safety principles

- Default mode is **PAPER_SANDBOX**.
- **REAL_LIVE** is never auto-enabled; requires transition token + env approval.
- Live **submit** requires `approval_id` and resolves broker credentials only via **SecretBroker** (never returned in API responses).
- Paper gateway **refuses** execution when mode is REAL_LIVE.
- Do not put API keys in source; use env + Drive encrypted store.

## Quick start

```bash
python -m pip install -e '.[test]'
pytest -q
```

### In-process trade flow

```python
from decimal import Decimal
from paper_live import (
    EnvironmentController,
    ExecutionGateway,
    InternalTradeFacade,
    OrderIntent,
    PaperAccount,
    RiskGuardian,
    VirtualMatchingEngine,
)
from paper_live.secrets import InMemorySecretStore, SecretBroker, SecretPolicy

controller = EnvironmentController()
account = PaperAccount(Decimal("1_000_000"))
gateway = ExecutionGateway(controller, VirtualMatchingEngine(account))
risk = RiskGuardian(controller, account)
secrets = SecretBroker(
    InMemorySecretStore({"toss-order": "..."}),
    SecretPolicy(live_secret_ids=frozenset({"toss-order"})),
)
facade = InternalTradeFacade(controller, risk, gateway, secret_broker=secrets)

intent = OrderIntent("005930", "BUY", Decimal("10"), client_order_id="demo-1")
preview = facade.preview(intent, Decimal("70000"))
fill = facade.submit(intent, Decimal("70000"))  # paper path
```

## Google Drive

### Encrypted API keys (`GoogleDriveSecretStore`)

Drive holds **ciphertext only** (`paper-live-encrypted-secrets.db`). Encryption key and OAuth token stay on the host.

```text
GOOGLE_DRIVE_ACCESS_TOKEN       # Drive API token
GOOGLE_DRIVE_SECRET_KEY         # 32-byte key (raw or urlsafe base64)
GOOGLE_DRIVE_SECRET_FILE_ID     # optional existing file id
GOOGLE_DRIVE_SECRET_FOLDER_ID   # optional parent folder
```

Wire into the facade:

```python
from paper_live.secrets import GoogleDriveSecretStore, SecretBroker, SecretPolicy

store = GoogleDriveSecretStore()  # reads env
broker = SecretBroker(store, SecretPolicy(live_secret_ids=frozenset({"toss-order", "kb-order"})))
facade = InternalTradeFacade(..., secret_broker=broker)
```

On REAL_LIVE `submit`, the facade calls `secret_broker.resolve(secret_id=..., mode="REAL_LIVE", capability="order.create")` before `BrokerRouter`.

### Market data archive (`GoogleDriveStorageAgent`)

```text
GOOGLE_DRIVE_DATA_ACCESS_TOKEN    # preferred
GOOGLE_DRIVE_ACCESS_TOKEN         # fallback
GOOGLE_DRIVE_DATA_SHARED_DRIVE_ID # optional shared drive
```

Datasets are written as versioned JSONL + `manifest.json` (checksum, row_count). Drive is an archive/distribution layer, not a database.

## Layout

```text
src/paper_live/
  trade_facade.py     # OrderIntent / OrderPreview / InternalTradeFacade
  environment.py
  execution.py
  risk.py
  secrets/            # SecretBroker, GoogleDriveSecretStore
  security/           # order-level LiveApprovalGate
  brokers/            # protocol, safe_router, toss, kb
  data_lake.py        # market dataset archive
  plugins/ agents.py ...
```

## Tests

```bash
pytest -vv --tb=short
# with coverage (CI):
pytest -vv --cov=paper_live --cov-report=term-missing
```

## License

See `LICENSE`.
