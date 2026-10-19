from __future__ import annotations

import hmac
import os
import re
import secrets
from datetime import datetime
from html import escape
from typing import Annotated

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from paper_live.secrets import GoogleDriveSecretStore, SecretRecord

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
SESSION_SECRET = os.getenv("SESSION_SECRET", "")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").strip().lower() in {"1", "true", "yes"}
ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,99}$")

app = FastAPI(title="Drive Secret Manager", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET or "invalid-development-secret-set-SESSION_SECRET",
    session_cookie="drive_secret_session",
    same_site="strict",
    https_only=COOKIE_SECURE,
    max_age=1800,
)

STYLE = """
<style>
:root{font-family:system-ui,sans-serif;color:#172033;background:#f4f6fa}
body{max-width:980px;margin:36px auto;padding:0 16px}
main{background:white;border:1px solid #dce2ec;border-radius:14px;padding:24px;box-shadow:0 8px 28px #1827440b}
h1{font-size:1.5rem;margin-top:0}h2{font-size:1.05rem;margin-top:28px}
label{display:block;font-size:.88rem;font-weight:600;margin:10px 0 4px}
input,select{box-sizing:border-box;width:100%;padding:10px;border:1px solid #cbd3e1;border-radius:8px;background:white}
button{border:0;border-radius:8px;padding:10px 14px;background:#1f4e8c;color:white;font-weight:650;cursor:pointer;margin-top:12px}
button.danger{background:#a52b36}table{border-collapse:collapse;width:100%;margin-top:12px;font-size:.9rem}
th,td{text-align:left;padding:10px 8px;border-bottom:1px solid #e7ebf2;vertical-align:top}
small,.muted{color:#667085}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.notice{padding:10px 12px;background:#eef5ff;border-radius:8px;margin:12px 0}.error{background:#fff0f0}
.inline{display:inline}.inline button{margin:0}.top{display:flex;justify-content:space-between;align-items:center;gap:16px}
@media(max-width:650px){.grid{grid-template-columns:1fr}table{font-size:.8rem}th,td{padding:7px 4px}}
</style>
"""


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf"] = token
    return token


def authenticated(request: Request) -> bool:
    return request.session.get("authenticated") is True


def check_csrf(request: Request, submitted: str) -> bool:
    expected = request.session.get("csrf", "")
    return isinstance(expected, str) and bool(expected) and hmac.compare_digest(expected, submitted)


def get_store() -> GoogleDriveSecretStore:
    if not ADMIN_PASSWORD or not SESSION_SECRET or len(SESSION_SECRET) < 32:
        raise RuntimeError("Admin password and a session secret of at least 32 characters must be configured")
    return GoogleDriveSecretStore()


def page(body: str, *, title: str = "Drive Secret Manager", status: int = 200) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>{escape(title)}</title>"
        f"{STYLE}</head><body><main>{body}</main></body></html>",
        status_code=status,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"},
    )


def login_page(request: Request, message: str = "") -> HTMLResponse:
    token = escape(csrf_token(request))
    note = f"<div class='notice error'>{escape(message)}</div>" if message else ""
    return page(
        f"<h1>Drive Secret Manager</h1><p class='muted'>Private credential administration</p>{note}"
        f"<form method='post' action='/login'><input type='hidden' name='csrf' value='{token}'>"
        f"<label>Username</label><input name='username' autocomplete='username' required>"
        f"<label>Password</label><input type='password' name='password' autocomplete='current-password' required>"
        f"<button type='submit'>Sign in</button></form>",
        title="Sign in",
    )


def read_records(store: GoogleDriveSecretStore) -> list[SecretRecord]:
    file_id = store._find_file_id()
    if not file_id:
        return []
    blob = store._request("GET", store._drive_file_url(file_id, alt_media=True))
    return sorted(store._decrypt(blob), key=lambda r: (r.provider.lower(), r.secret_id.lower()))


def dashboard(request: Request, message: str = "", *, error: bool = False) -> HTMLResponse:
    if not authenticated(request):
        return login_page(request)
    try:
        store = get_store()
        records = read_records(store)
    except Exception:
        # Never send provider responses, tokens, or exception details to the browser.
        note = "<div class='notice error'>Could not access the encrypted Drive vault. Check server configuration and logs.</div>"
        records = []
    else:
        note = (f"<div class='notice {'error' if error else ''}'>{escape(message)}</div>" if message else "")

    token = escape(csrf_token(request))
    rows = []
    for r in records:
        expiry = escape(r.expires_at or "—")
        scopes = escape(", ".join(r.scopes) or "—")
        rows.append(
            "<tr>"
            f"<td><strong>{escape(r.secret_id)}</strong><br><small>{escape(r.provider)}</small></td>"
            f"<td>{escape(r.environment)}</td><td>{scopes}</td><td>{expiry}</td>"
            f"<td>{escape(r.status)}</td><td><form class='inline' method='post' action='/revoke'>"
            f"<input type='hidden' name='csrf' value='{token}'>"
            f"<input type='hidden' name='secret_id' value='{escape(r.secret_id)}'>"
            f"<button class='danger' type='submit' onclick=\"return confirm('Revoke this credential?')\">Revoke</button>"
            "</form></td></tr>"
        )
    table = (
        "<table><thead><tr><th>Credential</th><th>Environment</th><th>Scopes</th>"
        "<th>Expires</th><th>Status</th><th>Action</th></tr></thead><tbody>"
        + ("".join(rows) if rows else "<tr><td colspan='6'>No credentials found.</td></tr>")
        + "</tbody></table>"
    )
    body = (
        "<div class='top'><div><h1>Drive Secret Manager</h1>"
        "<p class='muted'>Values are write-only; the old key is never displayed.</p></div>"
        f"<form method='post' action='/logout'><input type='hidden' name='csrf' value='{token}'>"
        "<button type='submit'>Sign out</button></form></div>"
        + note
        + "<h2>Add or replace credential</h2>"
        + f"<form method='post' action='/save'><input type='hidden' name='csrf' value='{token}'>"
        + "<div class='grid'><div><label>Credential ID</label><input name='secret_id' placeholder='openai-api' pattern='[A-Za-z0-9][A-Za-z0-9._-]{0,99}' required></div>"
        + "<div><label>Provider</label><input name='provider' placeholder='openai' maxlength='80' required></div>"
        + "<div><label>Environment</label><select name='environment'><option>PAPER_SANDBOX</option><option>VIRTUAL_BACKTEST</option><option>REAL_LIVE</option></select></div>"
        + "<div><label>Scopes (comma-separated)</label><input name='scopes' placeholder='model.invoke, market.read'></div>"
        + "<div><label>Expires at (optional ISO-8601 with timezone)</label><input name='expires_at' placeholder='2027-01-01T00:00:00+00:00'></div>"
        + "<div><label>New API key / token</label><input type='password' name='value' autocomplete='new-password' minlength='1' required></div></div>"
        + "<button type='submit'>Encrypt and save</button></form>"
        + "<h2>Stored credentials</h2>" + table
        + "<p class='muted'>Revocation is recorded in the encrypted vault. Also revoke compromised keys at their provider.</p>"
    )
    return page(body)


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return dashboard(request)


@app.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    csrf: Annotated[str, Form()],
) -> HTMLResponse | RedirectResponse:
    if not check_csrf(request, csrf):
        return login_page(request, "Session expired. Reload and try again.")
    if not ADMIN_PASSWORD or not SESSION_SECRET or len(SESSION_SECRET) < 32:
        return login_page(request, "Server authentication is not configured.",)
    if not (hmac.compare_digest(username, ADMIN_USERNAME) and hmac.compare_digest(password, ADMIN_PASSWORD)):
        return login_page(request, "Invalid username or password.")
    request.session.clear()
    request.session["authenticated"] = True
    request.session["csrf"] = secrets.token_urlsafe(32)
    return RedirectResponse("/", status_code=303)


@app.post("/logout")
def logout(request: Request, csrf: Annotated[str, Form()]) -> RedirectResponse | HTMLResponse:
    if not authenticated(request) or not check_csrf(request, csrf):
        return page("<h1>Session expired</h1><a href='/'>Return</a>", status=403)
    request.session.clear()
    return RedirectResponse("/", status_code=303)


@app.post("/save", response_class=HTMLResponse)
def save(
    request: Request,
    csrf: Annotated[str, Form()],
    secret_id: Annotated[str, Form()],
    provider: Annotated[str, Form()],
    environment: Annotated[str, Form()],
    value: Annotated[str, Form()],
    scopes: Annotated[str, Form()] = "",
    expires_at: Annotated[str, Form()] = "",
) -> HTMLResponse:
    if not authenticated(request):
        return login_page(request)
    if not check_csrf(request, csrf):
        return dashboard(request, "Session expired. Reload and try again.", error=True)
    secret_id, provider, value = secret_id.strip(), provider.strip(), value.strip()
    if not ID_PATTERN.fullmatch(secret_id) or not provider or not value:
        return dashboard(request, "Invalid ID, provider, or empty credential.", error=True)
    if environment not in {"PAPER_SANDBOX", "VIRTUAL_BACKTEST", "REAL_LIVE"}:
        return dashboard(request, "Invalid environment.", error=True)
    expiry = expires_at.strip() or None
    if expiry:
        try:
            parsed = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError
        except ValueError:
            return dashboard(request, "Expiry must be ISO-8601 and include a timezone.", error=True)
    try:
        record = SecretRecord(
            secret_id=secret_id,
            value=value,
            provider=provider[:80],
            environment=environment,
            scopes=tuple(sorted({s.strip() for s in scopes.split(",") if s.strip()})),
            expires_at=expiry,
            status="active",
        )
        get_store().put(record)
    except Exception:
        return dashboard(request, "Save failed. Check Drive access and server configuration.", error=True)
    return dashboard(request, f"Credential '{secret_id}' encrypted and saved.")


@app.post("/revoke", response_class=HTMLResponse)
def revoke(request: Request, csrf: Annotated[str, Form()], secret_id: Annotated[str, Form()]) -> HTMLResponse:
    if not authenticated(request):
        return login_page(request)
    if not check_csrf(request, csrf):
        return dashboard(request, "Session expired. Reload and try again.", error=True)
    if not ID_PATTERN.fullmatch(secret_id):
        return dashboard(request, "Invalid credential ID.", error=True)
    try:
        get_store().revoke(secret_id)
    except Exception:
        return dashboard(request, "Revocation failed. Check the credential ID and Drive access.", error=True)
    return dashboard(request, f"Credential '{secret_id}' revoked.")
