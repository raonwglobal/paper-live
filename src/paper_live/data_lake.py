from __future__ import annotations

import hashlib
import json
import os
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
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
    partition_count: int = 0
    partition_keys: tuple[str, ...] = ()


class DriveClient(Protocol):
    def upload(self, name: str, content: bytes, *, folder_id: str | None = None, mime_type: str = "application/octet-stream") -> str: ...
    def ensure_folder(self, name: str, *, parent_id: str | None = None) -> str: ...


class ReadableDriveClient(Protocol):
    def find_file(self, name: str, *, parent_id: str | None = None, mime_type: str | None = None) -> str | None: ...
    def list_files(self, *, parent_id: str, name_prefix: str | None = None) -> Sequence[Mapping[str, str]]: ...
    def download(self, file_id: str) -> bytes: ...


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
        url = f"https://www.googleapis.com/drive/v3/files?q={query}&fields=files(id,name,mimeType)&pageSize=100&{self._common_params()}"
        payload = json.loads(self._request("GET", url))
        files = payload.get("files", [])
        return files[0]["id"] if files else None

    def find_file(self, name: str, *, parent_id: str | None = None, mime_type: str | None = None) -> str | None:
        return self._find(name, parent_id, mime_type)

    def list_files(self, *, parent_id: str, name_prefix: str | None = None) -> Sequence[Mapping[str, str]]:
        clauses = [f"'{parent_id}' in parents", "trashed=false"]
        if name_prefix:
            escaped = name_prefix.replace("'", "''")
            clauses.append(f"name contains '{escaped}'")
        query = urllib.parse.quote(" and ".join(clauses))
        url = f"https://www.googleapis.com/drive/v3/files?q={query}&fields=files(id,name,mimeType)&pageSize=1000&{self._common_params()}"
        payload = json.loads(self._request("GET", url))
        return tuple(payload.get("files", ()))

    def download(self, file_id: str) -> bytes:
        url = f"https://www.googleapis.com/drive/v3/files/{urllib.parse.quote(file_id, safe='')}?alt=media&{self._common_params()}"
        return self._request("GET", url)

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

    def _resolve(self, path: str | None) -> Path:
        if not path:
            return self.root / "root"
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return self.root / path

    def ensure_folder(self, name: str, *, parent_id: str | None = None) -> str:
        folder = self._resolve(parent_id) / name
        folder.mkdir(parents=True, exist_ok=True)
        return str(folder)

    def upload(self, name: str, content: bytes, *, folder_id: str | None = None, mime_type: str = "application/octet-stream") -> str:
        target = self._resolve(folder_id) / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return str(target)

    def find_file(self, name: str, *, parent_id: str | None = None, mime_type: str | None = None) -> str | None:
        target = self._resolve(parent_id) / name
        return str(target) if target.is_file() or (mime_type == "application/vnd.google-apps.folder" and target.is_dir()) else None

    def list_files(self, *, parent_id: str, name_prefix: str | None = None) -> Sequence[Mapping[str, str]]:
        folder = self._resolve(parent_id)
        if not folder.is_dir():
            return ()
        return tuple(
            {
                "id": str(path),
                "name": path.name,
                "mimeType": "application/vnd.google-apps.folder" if path.is_dir() else "",
            }
            for path in folder.iterdir()
            if not name_prefix or path.name.startswith(name_prefix)
        )

    def download(self, file_id: str) -> bytes:
        return Path(file_id).read_bytes()


class GoogleDriveStorageAgent:
    """Versioned archive writer; dataset paths are materialized as Drive folders."""

    def __init__(self, client: DriveClient, *, folder_id: str | None = None, source: str = "paper-live"):
        self.client = client
        self.folder_id = folder_id
        self.source = source

    @staticmethod
    def _checksum(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def _validate_trade_date(trade_date: str) -> str:
        try:
            parsed = date.fromisoformat(str(trade_date))
        except ValueError as exc:
            raise ValueError("partition trade_date must be an ISO-8601 date") from exc
        if parsed < date(1900, 1, 1):
            raise ValueError("partition trade_date is outside supported range")
        return parsed.isoformat()

    def _dataset_folder(self, dataset: str, as_of: str) -> str:
        current: str | None = self.folder_id
        for part in [p for p in dataset.strip("/").split("/") if p] + [f"date={as_of.replace(':', '-')}"]:
            current = self.client.ensure_folder(part, parent_id=current)
        assert current is not None
        return current

    def _partition_folder(self, dataset: str, trade_date: str) -> str:
        current: str | None = self.folder_id
        for part in [p for p in dataset.strip("/").split("/") if p] + [f"trade_date={trade_date}"]:
            current = self.client.ensure_folder(part, parent_id=current)
        assert current is not None
        return current

    def _find_dataset_folder(self, dataset: str) -> str | None:
        current = self.folder_id
        readable = self._readable_client()
        for part in [p for p in dataset.strip("/").split("/") if p]:
            current = readable.find_file(part, parent_id=current, mime_type="application/vnd.google-apps.folder")
            if not current:
                return None
        return current

    def _readable_client(self) -> ReadableDriveClient:
        client = self.client
        if not all(hasattr(client, name) for name in ("find_file", "list_files", "download")):
            raise RuntimeError("configured Drive client does not support dataset reads")
        return client  # type: ignore[return-value]

    def read_partitioned_jsonl(self, dataset: str, *, trade_dates: Sequence[str] | None = None) -> tuple[dict[str, Any], ...]:
        """Read canonical/recovery date partitions without depending on an as-of folder."""
        readable = self._readable_client()
        dataset_folder = self._find_dataset_folder(dataset)
        if not dataset_folder:
            return ()
        wanted = {self._validate_trade_date(value) for value in trade_dates} if trade_dates else None
        rows: list[dict[str, Any]] = []
        for item in readable.list_files(parent_id=dataset_folder, name_prefix="trade_date="):
            name = str(item.get("name", ""))
            if not name.startswith("trade_date="):
                continue
            trade_date = name.split("=", 1)[1]
            if wanted is not None and trade_date not in wanted:
                continue
            partition_folder = str(item["id"])
            data_file = readable.find_file(f"{dataset.split('/')[-1]}.jsonl", parent_id=partition_folder)
            if not data_file:
                continue
            for line in readable.download(data_file).decode("utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    if self._validate_trade_date(str(row.get("trade_date", ""))) != trade_date:
                        raise ValueError("dataset row trade_date does not match partition")
                    rows.append(row)
        return tuple(sorted(rows, key=lambda row: (str(row.get("market", "")).upper(), str(row.get("symbol", "")), str(row.get("trade_date", "")))))

    def write_jsonl(self, dataset: str, rows: Sequence[dict[str, Any]], *, as_of: str, schema_version: str = "1.0", run_id: str | None = None, success_count: int = 0, failure_count: int = 0, source: str | None = None) -> DatasetManifest:
        payload = b"".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n" for row in rows)
        checksum = self._checksum(payload)
        folder = self._dataset_folder(dataset, as_of)
        self.client.upload(f"{dataset.split('/')[-1]}.jsonl", payload, folder_id=folder, mime_type="application/x-ndjson")
        manifest = DatasetManifest(dataset, as_of, len(rows), schema_version, source or self.source, checksum, run_id, success_count, failure_count, 0, ())
        self.client.upload("manifest.json", json.dumps(asdict(manifest), ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8"), folder_id=folder, mime_type="application/json")
        return manifest

    def write_partitioned_jsonl(self, dataset: str, partitions: Mapping[str, Sequence[dict[str, Any]]], *, as_of: str, schema_version: str = "1.0", run_id: str | None = None, success_count: int = 0, failure_count: int = 0, source: str | None = None) -> DatasetManifest:
        """Write deterministic date partitions and an aggregate index manifest."""
        normalized_partitions: dict[str, Sequence[dict[str, Any]]] = {}
        for raw_key, rows in partitions.items():
            trade_date = self._validate_trade_date(raw_key)
            if trade_date in normalized_partitions:
                raise ValueError(f"duplicate partition key after normalization: {trade_date}")
            normalized_partitions[trade_date] = rows
        partition_keys = tuple(sorted(normalized_partitions))
        checksummed_parts: list[dict[str, Any]] = []
        total_rows = 0
        for trade_date in partition_keys:
            rows = sorted(normalized_partitions[trade_date], key=lambda row: (str(row.get("market", "")), str(row.get("symbol", "")), str(row.get("trade_date", ""))))
            for row in rows:
                row_date = self._validate_trade_date(str(row.get("trade_date", "")))
                if row_date != trade_date:
                    raise ValueError(f"row trade_date {row_date} does not match partition {trade_date}")
            payload = b"".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n" for row in rows)
            folder = self._partition_folder(dataset, trade_date)
            file_name = f"{dataset.split('/')[-1]}.jsonl"
            self.client.upload(file_name, payload, folder_id=folder, mime_type="application/x-ndjson")
            markets = sorted({str(row.get("market", "")).strip().upper() for row in rows if row.get("market")})
            currencies = sorted({str(row.get("currency", "")).strip().upper() for row in rows if row.get("currency")})
            sources = sorted({str(row.get("source", "")).strip() for row in rows if row.get("source")})
            checksummed_parts.append({"trade_date": trade_date, "row_count": len(rows), "checksum_sha256": self._checksum(payload), "markets": markets, "currencies": currencies, "sources": sources})
            total_rows += len(rows)
        aggregate = {"dataset": dataset, "as_of": as_of, "schema_version": schema_version, "source": source or self.source, "run_id": run_id, "partitions": checksummed_parts}
        aggregate_bytes = json.dumps(aggregate, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        index_folder = self._dataset_folder(dataset, as_of)
        self.client.upload("partitions.json", aggregate_bytes, folder_id=index_folder, mime_type="application/json")
        manifest = DatasetManifest(dataset, as_of, total_rows, schema_version, source or self.source, self._checksum(aggregate_bytes), run_id, success_count, failure_count, len(partition_keys), partition_keys)
        self.client.upload("manifest.json", json.dumps(asdict(manifest), ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8"), folder_id=index_folder, mime_type="application/json")
        return manifest

    def _run_stage_folder(self, run_id: str, stage: str, trade_date: str) -> str:
        current: str | None = self.folder_id
        for part in ("runs", run_id, "execution", stage, f"trade_date={trade_date}"):
            current = self.client.ensure_folder(part, parent_id=current)
        assert current is not None
        return current

    def write_run_stage_jsonl(
        self,
        run_id: str,
        stage: str,
        trade_date: str,
        rows: Sequence[dict[str, Any]],
        *,
        schema_version: str = "1.0",
        source: str | None = None,
    ) -> DatasetManifest:
        """Persist a deterministic, idempotent run-scoped execution artifact."""
        if not run_id.strip():
            raise ValueError("run_id is required")
        if not stage.strip():
            raise ValueError("stage is required")
        normalized_date = self._validate_trade_date(trade_date)
        normalized_rows = sorted(
            (dict(row) for row in rows),
            key=lambda row: (
                str(row.get("event_key", "")),
                str(row.get("symbol", "")),
                str(row.get("client_order_id", "")),
                str(row.get("audit_id", "")),
                str(row.get("episode_id", "")),
            ),
        )
        payload = b"".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
            for row in normalized_rows
        )
        checksum = self._checksum(payload)
        folder = self._run_stage_folder(run_id, stage, normalized_date)
        file_id = self.client.upload(
            f"{stage}.jsonl", payload, folder_id=folder, mime_type="application/x-ndjson"
        )
        manifest_payload = {
            "run_id": run_id,
            "stage": stage,
            "trade_date": normalized_date,
            "row_count": len(normalized_rows),
            "checksum_sha256": checksum,
            "schema_version": schema_version,
            "source": source or self.source,
            "artifact_id": file_id,
        }
        self.client.upload(
            "manifest.json",
            json.dumps(manifest_payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8"),
            folder_id=folder,
            mime_type="application/json",
        )
        return DatasetManifest(
            dataset=f"runs/{run_id}/execution/{stage}",
            as_of=normalized_date,
            row_count=len(normalized_rows),
            schema_version=schema_version,
            source=source or self.source,
            checksum_sha256=checksum,
            run_id=run_id,
            partition_count=1,
            partition_keys=(normalized_date,),
        )

    def write_snapshot(self, dataset: str, rows: Sequence[dict[str, Any]], *, as_of: str, schema_version: str = "1.0", run_id: str | None = None, success_count: int = 0, failure_count: int = 0, source: str | None = None) -> DatasetManifest:
        return self.write_jsonl(dataset, rows, as_of=as_of, schema_version=schema_version, run_id=run_id, success_count=success_count, failure_count=failure_count, source=source)

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
