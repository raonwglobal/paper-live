from __future__ import annotations

import argparse
import csv
import os
import uuid
from datetime import date
from pathlib import Path

from .data_lake import DriveClient, GoogleDriveApiClient, GoogleDriveStorageAgent, LocalDriveMirror
from .market_data_collector import DailyMarketDataCollector
from .universe import Security, SecurityMaster
from .yfinance_provider import YFinanceDailyPriceProvider


def _load_universe(path: str) -> SecurityMaster:
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"symbol", "name", "market"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("universe CSV requires symbol,name,market columns")
        securities = []
        for row in reader:
            active = str(row.get("active", "true")).strip().lower() not in {"0", "false", "no"}
            securities.append(Security(
                symbol=str(row["symbol"]).strip(),
                name=str(row["name"]).strip(),
                market=str(row["market"]).strip().upper(),
                currency=str(row.get("currency") or "KRW").strip().upper(),
                active=active,
            ))
    return SecurityMaster(securities)


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect daily OHLCV data for a CSV security universe")
    parser.add_argument("--universe", required=True, help="CSV columns: symbol,name,market[,currency,active]")
    parser.add_argument("--start-date", required=True, type=date.fromisoformat)
    parser.add_argument("--end-date", required=True, type=date.fromisoformat)
    parser.add_argument("--dataset", default="market/daily-prices")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--storage", choices=("drive", "local"), default="drive")
    parser.add_argument("--local-dir", default="./paper-live-data")
    parser.add_argument("--drive-folder-id", default=os.getenv("GOOGLE_DRIVE_DATA_FOLDER_ID"))
    args = parser.parse_args()
    if args.end_date < args.start_date:
        parser.error("--end-date must be on or after --start-date")

    universe = _load_universe(args.universe)
    client: DriveClient
    if args.storage == "local":
        client = LocalDriveMirror(args.local_dir)
    else:
        client = GoogleDriveApiClient()
    storage = GoogleDriveStorageAgent(client, folder_id=args.drive_folder_id)
    collector = DailyMarketDataCollector(
        universe,
        lambda market: YFinanceDailyPriceProvider(market=market),
        storage,
        dataset=args.dataset,
    )
    report = collector.collect(
        args.start_date,
        args.end_date,
        run_id=args.run_id or str(uuid.uuid4()),
    )
    print(
        f"run_id={report.manifest.run_id} rows={report.manifest.row_count} "
        f"requested={report.requested} succeeded={report.succeeded} failed={report.failed}"
    )
    for market, symbol, error in report.failures:
        print(f"failed market={market} symbol={symbol} error={error}")
    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
