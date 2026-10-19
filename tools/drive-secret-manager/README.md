# Drive Secret Manager

A small, separate web UI for managing API credentials in the existing `paper-live` encrypted Google Drive secret store. It is intended to be operated by a background agent or a human administrator; it does not run trading or recommendation workflows.

## Features

- Add a credential, replace it without revealing the old value, inspect metadata, and revoke it.
- Reuses `paper_live.secrets.GoogleDriveSecretStore`: Drive stores AES-GCM ciphertext only.
- One administrator password, signed HttpOnly session cookie, CSRF token checks, no public registration.
- The UI never displays secret values; values are not logged.
- Binds to loopback by default.

## Run locally

From the repository root:

```bash
python -m pip install -e .
python -m pip install -r tools/drive-secret-manager/requirements.txt
cp tools/drive-secret-manager/.env.example tools/drive-secret-manager/.env
# Fill the environment values in .env; never commit it.
set -a
source tools/drive-secret-manager/.env
set +a
uvicorn --app-dir tools/drive-secret-manager app:app --host 127.0.0.1 --port 8787
```

Open http://127.0.0.1:8787. The app requires `ADMIN_PASSWORD`, `SESSION_SECRET`, `GOOGLE_DRIVE_ACCESS_TOKEN`, and `GOOGLE_DRIVE_SECRET_KEY`. Use a randomly generated 32-byte AES key (urlsafe-base64 encoded) and a long random session secret. The Drive token and encryption key must be provided through the host environment or a protected secret manager—not stored in the same Drive folder.

For deployment behind HTTPS, set `COOKIE_SECURE=true`, bind only to a private interface, and put the app behind an authenticated TLS reverse proxy/VPN. Do not expose this service directly to the public internet. Rotate the Google access token as required; this MVP uses the access token already supported by the current store and does not refresh OAuth tokens automatically.

## Secret fields

- `secret_id`: stable ID consumed by paper-live, e.g. `openai-api` or `toss-order`
- `provider`: provider name
- `environment`: `PAPER_SANDBOX`, `VIRTUAL_BACKTEST`, or `REAL_LIVE`
- `scopes`: comma-separated capability labels
- `expires_at`: optional ISO-8601 timestamp with timezone
- `value`: API key/token/credential material (write-only in the UI)

Deleting a record marks it revoked; it does not physically erase historical ciphertext immediately. This is deliberate for safer revocation/audit semantics. To invalidate a provider key, revoke it at the provider as well.

## Security limitations

This is a minimal single-admin MVP, not a multi-user vault. Run only on loopback or inside a private network. The AES key and Drive OAuth token are bootstrap secrets and must remain outside Drive. Use least-privilege Drive access, HTTPS, backups, and a documented key-recovery process. The project does not claim a live Drive integration test until configured credentials are supplied and the test is run.
