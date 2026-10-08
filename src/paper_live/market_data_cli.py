from __future__ import annotations

import argparse
import csv
import json
import os
import uuid
from datetime import date
from pathlib import Path

from .data_lake import DriveClient, GoogleDriveApiClient, GoogleDriveStorageAgent, LocalDriveMirror
from .market_data_collector import DailyMarketDataCollector
from .universe import Security, SecurityMaster
from .yfinance_provider import YFinanceDailyPriceProvider


def _load_universe(paths: list[str]) -> SecurityMaster:
    master = SecurityMaster()
    for path in paths:
        with Path(path).open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            required = {"symbol", "name", "market"}
            if not reader.fieldnames or not required.issubset(reader.fieldnames):
                raise ValueError(f"universe CSV requires symbol,name,market columns: {path}")
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
        master.merge(securities)
    return master


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect daily OHLCV data for one or more CSV security universes")
    parser.add_argument(
        "--universe",
        required=True,
        action="append",
        help="CSV columns: symbol,name,market[,currency,active]; repeat to merge sources",
    )
    parser.add_argument("--start-date", required=True, type=date.fromisoformat)
    parser.add_argument("--end-date", required=True, type=date.fromisoformat)
    parser.add_argument("--dataset", default="market/daily-prices")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--storage", choices=("auto", "drive", "local"), default="auto")
    parser.add_argument("--local-dir", default="./paper-live-data")
    parser.add_argument("--drive-folder-id", default=os.getenv("GOOGLE_DRIVE_DATA_FOLDER_ID"))
    parser.add_argument("--report-json", default=None, help="Write a machine-readable run summary")
    parser.add_argument("--report-csv", default=None, help="Write per-symbol failures as CSV")
    args = parser.parse_args()
    if args.end_date < args.start_date:
        parser.error("--end-date must be on or after --start-date")

    universe = _load_universe(args.universe)
    storage_target = args.storage
    if storage_target == "auto":
        storage_target = "drive" if os.getenv("GOOGLE_DRIVE_DATA_ACCESS_TOKEN") else "local"

    client: DriveClient
    if storage_target == "local":
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

    if args.report_json:
        report_path = Path(args.report_json)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": report.manifest.run_id,
            "dataset": args.dataset,
            "start_date": args.start_date.isoformat(),
            "end_date": args.end_date.isoformat(),
            "storage": storage_target,
            "universe": {
                "active_count": len(universe.active()),
                "markets": list(universe.markets()),
                "count_by_market": {market: len(universe.active(market)) for market in universe.markets()},
            },
            "row_count": report.manifest.row_count,
            "requested": report.requested,
            "succeeded": report.succeeded,
            "failed": report.failed,
            "quality": {
                "passed": report.quality.passed,
                "row_count": report.quality.row_count,
                "duplicate_count": report.quality.duplicate_count,
                "invalid_count": report.quality.invalid_count,
                "missing_close_count": report.quality.missing_close_count,
                "date_out_of_range_count": report.quality.date_out_of_range_count,
            },
            "failures": [
                {"market": market, "symbol": symbol, "error": error}
                for market, symbol, error in report.failures
            ],
        }
        report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.report_csv:
        report_path = Path(args.report_csv)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=("market", "symbol", "error"))
            writer.writeheader()
            writer.writerows(
                {"market": market, "symbol": symbol, "error": error}
                for market, symbol, error in report.failures
            )
    return 0 if report.failed == 0 and report.quality.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
