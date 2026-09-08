from __future__ import annotations

import hashlib
import json
import os
import urllib.parse
import urllib.request
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class DatasetManifest:
    dataset: str
    as_of: str
    row_count: int
    schema_version: str = "1.0"
    source: str = "unknown"
    checksum_sha256: str = ""


class DriveClient(Protocol):
    """Minimal Google Drive boundary; implementations own OAuth and transport."""

    def upload(
        self, name: str, content: bytes, *, folder_id: str | None = None, mime_type: str = "application/octet-stream"
    ) -> str: ...


class GoogleDriveApiClient:
    """Minimal Google Drive v3 client for idempotent dataset artifacts."""

    def __init__(self, *, access_token: str | None = None, shared_drive_id: str | None = None, timeout: int = 30):
        self.access_token = (
            access_token or os.getenv("GOOGLE_DRIVE_DATA_ACCESS_TOKEN") or os.getenv("GOOGLE_DRIVE_ACCESS_TOKEN")
        )
        self.shared_drive_id = shared_drive_id or os.getenv("GOOGLE_DRIVE_DATA_SHARED_DRIVE_ID")
        self.timeout = timeout
        if not self.access_token:
            raise RuntimeError("Google Drive access token is required")

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
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return response.read()
        except Exception as exc:
            raise RuntimeError(f"Google Drive request failed: {type(exc).__name__}") from exc

    def _common_params(self) -> str:
        params = "supportsAllDrives=true"
        if self.shared_drive_id:
            params += "&includeItemsFromAllDrives=true&corpora=drive&driveId=" + urllib.parse.quote(
                self.shared_drive_id
            )
        return params

    def _find(self, name: str, folder_id: str | None) -> str | None:
        escaped = name.replace("'", "''")
        clauses = [f"name='{escaped}'", "trashed=false"]
        if folder_id:
            clauses.append(f"'{folder_id}' in parents")
        query = urllib.parse.quote(" and ".join(clauses))
        url = f"https://www.googleapis.com/drive/v3/files?q={query}&fields=files(id,name)&pageSize=10&{self._common_params()}"
        payload = json.loads(self._request("GET", url))
        files = payload.get("files", [])
        return files[0]["id"] if files else None

    def upload(
        self, name: str, content: bytes, *, folder_id: str | None = None, mime_type: str = "application/octet-stream"
    ) -> str:
        existing = self._find(name, folder_id)
        if existing:
            url = f"https://www.googleapis.com/upload/drive/v3/files/{urllib.parse.quote(existing, safe='')}?uploadType=media&{self._common_params()}"
            self._request("PATCH", url, content, mime_type)
            return existing
        metadata: dict[str, object] = {"name": name}
        if folder_id:
            metadata["parents"] = [folder_id]
        boundary = "paper-live-" + hashlib.sha256(content).hexdigest()[:16]
        body = (
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode()
            + json.dumps(metadata).encode()
            + f"\r\n--{boundary}\r\nContent-Type: {mime_type}\r\n\r\n".encode()
            + content
            + f"\r\n--{boundary}--\r\n".encode()
        )
        url = f"https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id&{self._common_params()}"
        return json.loads(self._request("POST", url, body, f"multipart/related; boundary={boundary}"))["id"]


class LocalDriveMirror:
    """Filesystem mirror used for tests and offline operation."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def upload(
        self, name: str, content: bytes, *, folder_id: str | None = None, mime_type: str = "application/octet-stream"
    ) -> str:
        target = self.root / (folder_id or "root") / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return str(target)


class GoogleDriveStorageAgent:
    """Versioned dataset writer. Drive is a distribution/archive layer, not a database."""

    def __init__(self, client: DriveClient, *, folder_id: str | None = None, source: str = "paper-live"):
        self.client = client
        self.folder_id = folder_id
        self.source = source

    @staticmethod
    def _checksum(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def write_jsonl(
        self, dataset: str, rows: Sequence[dict[str, Any]], *, as_of: str, schema_version: str = "1.0"
    ) -> DatasetManifest:
        payload = b"".join(
            (json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n")
            for row in rows
        )
        checksum = self._checksum(payload)
        safe_date = as_of.replace(":", "-")
        name = f"{dataset}/date={safe_date}/{dataset}.jsonl"
        self.client.upload(name, payload, folder_id=self.folder_id, mime_type="application/x-ndjson")
        manifest = DatasetManifest(dataset, as_of, len(rows), schema_version, self.source, checksum)
        self.client.upload(
            f"{dataset}/date={safe_date}/manifest.json",
            json.dumps(asdict(manifest), ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8"),
            folder_id=self.folder_id,
            mime_type="application/json",
        )
        return manifest

    def write_snapshot(
        self, dataset: str, rows: Sequence[dict[str, Any]], *, as_of: str, schema_version: str = "1.0"
    ) -> DatasetManifest:
        return self.write_jsonl(dataset, rows, as_of=as_of, schema_version=schema_version)

    def validate_row_timestamps(self, rows: Sequence[dict[str, Any]]) -> None:
        for row in rows:
            if "available_at" not in row or "effective_date" not in row:
                raise ValueError("dataset rows must include effective_date and available_at")
            if row["available_at"] < row["effective_date"]:
                raise ValueError("available_at cannot precede effective_date")
