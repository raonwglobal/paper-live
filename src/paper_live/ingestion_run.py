from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from typing import Protocol


class ArtifactWriter(Protocol):
    def upload(self, name: str, content: bytes, *, folder_id: str | None = None,
               mime_type: str = "application/octet-stream") -> str: ...


@dataclass(frozen=True)
class IngestionFailure:
    market: str
    symbol: str
    start_date: str
    end_date: str
    error_type: str
    error_message: str
    attempts: int
    retryable: bool = True


@dataclass(frozen=True)
class IngestionRunManifest:
    run_id: str
    started_at: str
    finished_at: str
    status: str
    market: str
    start_date: str
    end_date: str
    requested_symbols: int
    succeeded_symbols: int
    failed_symbols: int
    rows_collected: int
    retryable_failures: int
    non_retryable_failures: int
    dataset: str | None = None
    dataset_checksum_sha256: str | None = None
    schema_version: str = "ingestion-run-v1"

    @property
    def is_complete(self) -> bool:
        return self.status == "completed"


class FailureQueue:
    """Deterministic, de-duplicated retry queue for failed symbol/date ranges."""

    def __init__(self, failures: Iterable[IngestionFailure] = ()) -> None:
        self._items: dict[tuple[str, str, str, str], IngestionFailure] = {}
        self.extend(failures)

    def add(self, failure: IngestionFailure) -> None:
        key = (failure.market, failure.symbol, failure.start_date, failure.end_date)
        previous = self._items.get(key)
        if previous is None or failure.attempts >= previous.attempts:
            self._items[key] = failure

    def extend(self, failures: Iterable[IngestionFailure]) -> None:
        for failure in failures:
            self.add(failure)

    def retryable(self) -> list[IngestionFailure]:
        return sorted((item for item in self._items.values() if item.retryable),
                      key=lambda item: (item.market, item.symbol, item.start_date, item.end_date))

    def all(self) -> list[IngestionFailure]:
        return sorted(self._items.values(), key=lambda item: (item.market, item.symbol, item.start_date, item.end_date))

    def to_jsonl(self) -> bytes:
        return b"".join(json.dumps(asdict(item), ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":")).encode("utf-8") + b"\n" for item in self.all())


class IngestionRunLedger:
    """Persists run/failure artifacts so interrupted collection can be resumed safely."""

    def __init__(self, writer: ArtifactWriter, *, folder_id: str | None = None) -> None:
        self.writer = writer
        self.folder_id = folder_id

    @staticmethod
    def new_run_id(*, market: str, start_date: date, end_date: date, symbols: Iterable[str]) -> str:
        canonical = json.dumps({"market": market, "start_date": start_date.isoformat(),
                                "end_date": end_date.isoformat(), "symbols": sorted(set(symbols))},
                               sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(canonical).hexdigest()[:24]

    def write(self, manifest: IngestionRunManifest, failures: FailureQueue) -> tuple[str, str]:
        root = self.folder_id
        # Materialize the same logical hierarchy on Drive and on the local mirror.
        # Writers that only implement upload retain the legacy flat-name behavior.
        ensure_folder = getattr(self.writer, "ensure_folder", None)
        if callable(ensure_folder):
            runs_folder = ensure_folder("runs", parent_id=root)
            market_folder = ensure_folder(manifest.market, parent_id=runs_folder)
            run_folder = ensure_folder(manifest.run_id, parent_id=market_folder)
            manifest_name = "manifest.json"
            failure_name = "failures.jsonl"
            target_folder = run_folder
        else:
            prefix = f"runs/{manifest.market}/{manifest.run_id}"
            manifest_name = f"{prefix}/manifest.json"
            failure_name = f"{prefix}/failures.jsonl"
            target_folder = root
        manifest_id = self.writer.upload(manifest_name,
                                         json.dumps(asdict(manifest), ensure_ascii=False, sort_keys=True,
                                                    indent=2).encode("utf-8"), folder_id=target_folder,
                                         mime_type="application/json")
        failure_id = self.writer.upload(failure_name, failures.to_jsonl(),
                                        folder_id=target_folder, mime_type="application/x-ndjson")
        return manifest_id, failure_id


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def build_manifest(*, run_id: str, started_at: str, market: str, start_date: date, end_date: date,
                   requested_symbols: int, succeeded_symbols: int, rows_collected: int,
                   failures: FailureQueue, dataset: str | None = None,
                   dataset_checksum_sha256: str | None = None, finished_at: str | None = None) -> IngestionRunManifest:
    all_failures = failures.all()
    retryable = sum(item.retryable for item in all_failures)
    status = "completed" if not all_failures else "completed_with_failures"
    if succeeded_symbols == 0 and requested_symbols > 0:
        status = "failed"
    return IngestionRunManifest(run_id=run_id, started_at=started_at, finished_at=finished_at or utc_now(),
                                status=status, market=market, start_date=start_date.isoformat(),
                                end_date=end_date.isoformat(), requested_symbols=requested_symbols,
                                succeeded_symbols=succeeded_symbols, failed_symbols=len(all_failures),
                                rows_collected=rows_collected, retryable_failures=retryable,
                                non_retryable_failures=len(all_failures) - retryable, dataset=dataset,
                                dataset_checksum_sha256=dataset_checksum_sha256)
