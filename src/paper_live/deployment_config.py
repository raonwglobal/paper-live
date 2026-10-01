from __future__ import annotations

import csv
import os
from pathlib import Path

from .data_lake import GoogleDriveApiClient, GoogleDriveStorageAgent
from .universe import Security, SecurityMaster


def load_security_master_csv(path: str | Path) -> SecurityMaster:
    """Load a version-controlled or deployment-mounted CSV security universe."""
    required = {"symbol", "name", "market"}
    securities: list[Security] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = set(reader.fieldnames or ())
        missing = required - columns
        if missing:
            raise ValueError(f"universe CSV missing required columns: {', '.join(sorted(missing))}")
        for line_number, row in enumerate(reader, start=2):
            symbol = (row.get("symbol") or "").strip()
            name = (row.get("name") or "").strip()
            market = (row.get("market") or "").strip().upper()
            currency = (row.get("currency") or "KRW").strip().upper()
            active_raw = (row.get("active") or "true").strip().lower()
            if active_raw not in {"true", "false", "1", "0", "yes", "no"}:
                raise ValueError(f"invalid active value at CSV line {line_number}")
            if not symbol or not name or not market or not currency:
                raise ValueError(f"blank required value at CSV line {line_number}")
            securities.append(Security(
                symbol=symbol,
                name=name,
                market=market,
                currency=currency,
                active=active_raw in {"true", "1", "yes"},
            ))
    if not securities:
        raise ValueError("universe CSV contains no securities")
    return SecurityMaster(securities)


def build_google_drive_storage() -> GoogleDriveStorageAgent:
    """Create the production Drive archive adapter without exposing credentials."""
    token = os.getenv("GOOGLE_DRIVE_DATA_ACCESS_TOKEN") or os.getenv("GOOGLE_DRIVE_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("Google Drive token is missing; configure GOOGLE_DRIVE_DATA_ACCESS_TOKEN")
    folder_id = os.getenv("GOOGLE_DRIVE_DATA_FOLDER_ID")
    client = GoogleDriveApiClient(access_token=token)
    return GoogleDriveStorageAgent(client, folder_id=folder_id, source="paper-live-market-data")
