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
    run_id: str | None = None
    success_count: int = 0
    failure_count: int = 0


class DriveClient(Protocol):
    def upload(self, name: str, content: bytes, *, folder_id: str | None = None, mime_type: str = "application/octet-stream") -> str: ...
    def ensure_folder(self, name: str, *, parent_id: str | None = None) -> str: ...


class GoogleDriveApiClient:
    """Small Drive v3 client with idempotent folder/file upserts."""

    def __init__(self, *, access_token: str | None = None, shared_drive_id: str | None = None, timeout: int = 30):
        self.access_token = access_token or os.getenv("GOOGLE_DRIVE_DATA_ACCESS_TOKEN") or os.getenv("GOOGLE_DRIVE_ACCESS_TOKEN")
        self.shared_drive_id = shared_drive_id or os.getenv("GOOGLE_DRIVE_DATA_SHARED_DRIVE_ID")
        self.timeout = timeout
        if not self.access_token:
            raise RuntimeError("Google Drive access token is required")

    def _request(self, method: str, url: str, data: bytes | None = None, content_type: str = "application/json") -> bytes:
        req = urllib.request.Request(url, data=data, method=method, headers={"Authorization": f"Bearer {self.access_token}", "Content-Type": content_type})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return response.read()
        except Exception as exc:
            raise RuntimeError(f"Google Drive request failed: {type(exc).__name__}") from exc

    def _common_params(self) -> str:
        params = "supportsAllDrives=true"
        if self.shared_drive_id:
            params += "&includeItemsFromAllDrives=true&corpora=drive&driveId=" + urllib.parse.quote(self.shared_drive_id)
        return params

    def _find(self, name: str, folder_id: str | None, mime_type: str | None = None) -> str | None:
        escaped = name.replace("'", "''")
        clauses = [f"name='{escaped}'", "trashed=false"]
        if folder_id:
            clauses.append(f"'{folder_id}' in parents")
        if mime_type:
            clauses.append(f"mimeType='{mime_type}'")
        query = urllib.parse.quote(" and ".join(clauses))
        url = f"https://www.googleapis.com/drive/v3/files?q={query}&fields=files(id,name,mimeType)&pageSize=10&{self._common_params()}"
        payload = json.loads(self._request("GET", url))
        files = payload.get("files", [])
        return files[0]["id"] if files else None

    def ensure_folder(self, name: str, *, parent_id: str | None = None) -> str:
        folder_mime = "application/vnd.google-apps.folder"
        existing = self._find(name, parent_id, folder_mime)
        if existing:
            return existing
        metadata: dict[str, object] = {"name": name, "mimeType": folder_mime}
        if parent_id:
            metadata["parents"] = [parent_id]
        url = f"https://www.googleapis.com/drive/v3/files?fields=id&{self._common_params()}"
        return json.loads(self._request("POST", url, json.dumps(metadata).encode("utf-8"), "application/json"))["id"]

    def upload(self, name: str, content: bytes, *, folder_id: str | None = None, mime_type: str = "application/octet-stream") -> str:
        existing = self._find(name, folder_id)
        if existing:
            url = f"https://www.googleapis.com/upload/drive/v3/files/{urllib.parse.quote(existing, safe='')}?uploadType=media&{self._common_params()}"
            self._request("PATCH", url, content, mime_type)
            return existing
        metadata: dict[str, object] = {"name": name, "mimeType": mime_type}
        if folder_id:
            metadata["parents"] = [folder_id]
        boundary = "paper-live-" + hashlib.sha256(content).hexdigest()[:16]
        body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode() + json.dumps(metadata).encode() + f"\r\n--{boundary}\r\nContent-Type: {mime_type}\r\n\r\n".encode() + content + f"\r\n--{boundary}--\r\n".encode())
        url = f"https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id&{self._common_params()}"
        return json.loads(self._request("POST", url, body, f"multipart/related; boundary={boundary}"))["id"]


class LocalDriveMirror:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def ensure_folder(self, name: str, *, parent_id: str | None = None) -> str:
        folder = self.root / (parent_id or "root") / name
        folder.mkdir(parents=True, exist_ok=True)
        return str(folder)

    def upload(self, name: str, content: bytes, *, folder_id: str | None = None, mime_type: str = "application/octet-stream") -> str:
        target = Path(folder_id or str(self.root / "root")) / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return str(target)


class GoogleDriveStorageAgent:
    """Versioned archive writer; dataset paths are materialized as Drive folders."""

    def __init__(self, client: DriveClient, *, folder_id: str | None = None, source: str = "paper-live"):
        self.client = client
        self.folder_id = folder_id
        self.source = source

    @staticmethod
    def _checksum(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def _dataset_folder(self, dataset: str, as_of: str) -> str:
        current = self.folder_id
        for part in [p for p in dataset.strip("/").split("/") if p] + [f"date={as_of.replace(':', '-')}"]:
            current = self.client.ensure_folder(part, parent_id=current)
        return current

    def write_jsonl(self, dataset: str, rows: Sequence[dict[str, Any]], *, as_of: str, schema_version: str = "1.0", run_id: str | None = None, success_count: int = 0, failure_count: int = 0) -> DatasetManifest:
        payload = b"".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n" for row in rows)
        checksum = self._checksum(payload)
        folder = self._dataset_folder(dataset, as_of)
        self.client.upload(f"{dataset.split('/')[-1]}.jsonl", payload, folder_id=folder, mime_type="application/x-ndjson")
        manifest = DatasetManifest(dataset, as_of, len(rows), schema_version, self.source, checksum, run_id, success_count, failure_count)
        self.client.upload("manifest.json", json.dumps(asdict(manifest), ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8"), folder_id=folder, mime_type="application/json")
        return manifest

    def write_snapshot(self, dataset: str, rows: Sequence[dict[str, Any]], *, as_of: str, schema_version: str = "1.0", run_id: str | None = None, success_count: int = 0, failure_count: int = 0) -> DatasetManifest:
        return self.write_jsonl(dataset, rows, as_of=as_of, schema_version=schema_version, run_id=run_id, success_count=success_count, failure_count=failure_count)

    def write_run_manifest(self, run_id: str, manifest: dict[str, Any], *, folder_name: str = "runs") -> str:
        folder = self.client.ensure_folder(folder_name, parent_id=self.folder_id)
        safe = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        return self.client.upload(f"{run_id}.json", safe, folder_id=folder, mime_type="application/json")

    def validate_row_timestamps(self, rows: Sequence[dict[str, Any]]) -> None:
        for row in rows:
            if "available_at" not in row or "effective_date" not in row:
                raise ValueError("dataset rows must include effective_date and available_at")
            if row["available_at"] < row["effective_date"]:
                raise ValueError("available_at cannot precede effective_date")
