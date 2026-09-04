from __future__ import annotations

import hashlib
import json
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
