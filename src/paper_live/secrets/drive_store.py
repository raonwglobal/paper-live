from __future__ import annotations

import base64
import json
import os
import secrets as pysecrets
import sqlite3
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


@dataclass(frozen=True)
class SecretRecord:
    secret_id: str
    value: str
    provider: str
    environment: str
    scopes: tuple[str, ...] = ()
    expires_at: str | None = None
    status: str = "active"


class GoogleDriveSecretStore:
    """Encrypted SQLite-like secret store persisted as a single encrypted Drive file.

    The Drive file contains only AES-256-GCM ciphertext. The encryption key and
    Google OAuth access token stay outside Drive. Secret values are never logged.
    """

    FILE_NAME = "paper-live-encrypted-secrets.db"

    def __init__(
        self, *, access_token: str | None = None, encryption_key: bytes | None = None, file_id: str | None = None
    ):
        self.access_token = access_token or os.getenv("GOOGLE_DRIVE_ACCESS_TOKEN")
        raw_key = encryption_key or self._key_from_env()
        if not self.access_token:
            raise RuntimeError("GOOGLE_DRIVE_ACCESS_TOKEN is required")
        if len(raw_key) != 32:
            raise ValueError("GOOGLE_DRIVE_SECRET_KEY must be exactly 32 bytes (base64 or raw)")
        self.encryption_key = raw_key
        self.file_id = file_id or os.getenv("GOOGLE_DRIVE_SECRET_FILE_ID")
        self.drive_id = os.getenv("GOOGLE_DRIVE_SECRET_DRIVE_ID")

    @staticmethod
    def _key_from_env() -> bytes:
        value = os.getenv("GOOGLE_DRIVE_SECRET_KEY")
        if not value:
            raise RuntimeError("GOOGLE_DRIVE_SECRET_KEY is required")
        try:
            decoded = base64.urlsafe_b64decode(value.encode())
            if len(decoded) == 32:
                return decoded
        except Exception:
            pass
        return value.encode()

    def _request(
        self, method: str, url: str, data: bytes | None = None, content_type: str = "application/json"
    ) -> bytes:
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={"Authorization": f"Bearer {self.access_token}", "Content-Type": content_type},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                return response.read()
        except Exception as exc:
            raise RuntimeError(f"Google Drive request failed: {type(exc).__name__}") from exc

    def _drive_query_params(self) -> str:
        params = {"supportsAllDrives": "true"}
        drive_id = getattr(self, "drive_id", None)
        if drive_id:
            params.update({"includeItemsFromAllDrives": "true", "corpora": "drive", "driveId": drive_id})
        return urllib.parse.urlencode(params)

    def _drive_file_url(self, file_id: str, *, alt_media: bool = False) -> str:
        params = self._drive_query_params()
        if alt_media:
            params += "&alt=media"
        return f"https://www.googleapis.com/drive/v3/files/{urllib.parse.quote(file_id, safe='')}?{params}"

    def _encrypt(self, records: list[SecretRecord]) -> bytes:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "secrets.db"
            conn = sqlite3.connect(path)
            try:
                conn.execute(
                    "CREATE TABLE secrets (secret_id TEXT PRIMARY KEY, provider TEXT NOT NULL, environment TEXT NOT NULL, value TEXT NOT NULL, scopes TEXT NOT NULL, expires_at TEXT, status TEXT NOT NULL, updated_at TEXT NOT NULL)"
                )
                now = datetime.now(UTC).isoformat()
                for r in records:
                    conn.execute(
                        "INSERT INTO secrets VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            r.secret_id,
                            r.provider,
                            r.environment,
                            r.value,
                            json.dumps(r.scopes),
                            r.expires_at,
                            r.status,
                            now,
                        ),
                    )
                conn.commit()
            finally:
                conn.close()
            plaintext = path.read_bytes()
        nonce = pysecrets.token_bytes(12)
        ciphertext = AESGCM(self.encryption_key).encrypt(nonce, plaintext, b"paper-live-secret-store:v1")
        return b"PLSECRETS1" + nonce + ciphertext

    def _decrypt(self, blob: bytes) -> list[SecretRecord]:
        if not blob.startswith(b"PLSECRETS1"):
            raise RuntimeError("unsupported secret store format")
        plaintext = AESGCM(self.encryption_key).decrypt(blob[10:22], blob[22:], b"paper-live-secret-store:v1")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "secrets.db"
            path.write_bytes(plaintext)
            conn = sqlite3.connect(path)
            try:
                rows = conn.execute(
                    "SELECT secret_id, provider, environment, value, scopes, expires_at, status FROM secrets"
                ).fetchall()
            finally:
                conn.close()
        return [SecretRecord(row[0], row[3], row[1], row[2], tuple(json.loads(row[4])), row[5], row[6]) for row in rows]

    def _download(self) -> bytes | None:
        if not getattr(self, "file_id", None):
            return None
        return self._request("GET", self._drive_file_url(self.file_id, alt_media=True))

    def _find_file_id(self) -> str | None:
        file_id = getattr(self, "file_id", None)
        if file_id:
            return file_id
        query = urllib.parse.quote(f"name='{self.FILE_NAME}' and trashed=false")
        params = self._drive_query_params() + "&fields=files(id,name)"
        payload = json.loads(
            self._request("GET", f"https://www.googleapis.com/drive/v3/files?q={query}&{params}")
        )
        files = payload.get("files", [])
        if not files:
            return None
        self.file_id = files[0]["id"]
        return self.file_id

    def _upload(self, blob: bytes) -> str:
        boundary = "paperlive-" + pysecrets.token_hex(12)
        folder_id = os.getenv("GOOGLE_DRIVE_SECRET_FOLDER_ID")
        metadata: dict[str, object] = {"name": self.FILE_NAME}
        if folder_id:
            metadata["parents"] = [folder_id]
        metadata_bytes = json.dumps(metadata).encode()
        body = (
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode()
            + metadata_bytes
            + f"\r\n--{boundary}\r\nContent-Type: application/octet-stream\r\n\r\n".encode()
            + blob
            + f"\r\n--{boundary}--\r\n".encode()
        )
        params = urllib.parse.urlencode({"uploadType": "multipart", "fields": "id", "supportsAllDrives": "true"})
        result = json.loads(
            self._request(
                "POST",
                f"https://www.googleapis.com/upload/drive/v3/files?{params}",
                body,
                f"multipart/related; boundary={boundary}",
            )
        )
        self.file_id = result["id"]
        return self.file_id

    def _update(self, file_id: str, blob: bytes) -> None:
        params = urllib.parse.urlencode({"uploadType": "media", "supportsAllDrives": "true"})
        self._request(
            "PATCH",
            f"https://www.googleapis.com/upload/drive/v3/files/{urllib.parse.quote(file_id, safe='')}?{params}",
            blob,
            "application/octet-stream",
        )

    def get(self, secret_id: str) -> str:
        file_id = self._find_file_id()
        if not file_id:
            raise KeyError(secret_id)
        records = self._decrypt(self._request("GET", self._drive_file_url(file_id, alt_media=True)))
        for record in records:
            if record.secret_id != secret_id or record.status != "active":
                continue
            if record.expires_at:
                try:
                    expires = datetime.fromisoformat(record.expires_at.replace("Z", "+00:00"))
                except ValueError as exc:
                    raise RuntimeError("invalid secret expiration metadata") from exc
                if expires.tzinfo is None:
                    raise RuntimeError("secret expiration metadata must include a timezone")
                if expires <= datetime.now(UTC):
                    raise KeyError(secret_id)
            return record.value
        raise KeyError(secret_id)

    def put(self, record: SecretRecord) -> None:
        file_id = self._find_file_id()
        records = []
        if file_id:
            records = self._decrypt(self._request("GET", self._drive_file_url(file_id, alt_media=True)))
        records = [r for r in records if r.secret_id != record.secret_id]
        records.append(record)
        blob = self._encrypt(records)
        if file_id:
            self._update(file_id, blob)
        else:
            self._upload(blob)

    def revoke(self, secret_id: str) -> None:
        file_id = self._find_file_id()
        if not file_id:
            raise KeyError(secret_id)
        records = self._decrypt(self._request("GET", self._drive_file_url(file_id, alt_media=True)))
        found = False
        updated = []
        for r in records:
            if r.secret_id == secret_id:
                found = True
                updated.append(
                    SecretRecord(r.secret_id, r.value, r.provider, r.environment, r.scopes, r.expires_at, "revoked")
                )
            else:
                updated.append(r)
        if not found:
            raise KeyError(secret_id)
        self._update(file_id, self._encrypt(updated))
