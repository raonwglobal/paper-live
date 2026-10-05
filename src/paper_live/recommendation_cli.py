from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime
from pathlib import Path

from .data_lake import DriveClient, GoogleDriveApiClient, GoogleDriveStorageAgent, LocalDriveMirror
from .recommendation_pipeline import RecommendationPipeline


def _storage(args: argparse.Namespace) -> tuple[GoogleDriveStorageAgent, str]:
    target = args.storage
    if target == "auto":
        target = "drive" if os.getenv("GOOGLE_DRIVE_DATA_ACCESS_TOKEN") else "local"
    client: DriveClient
    if target == "drive":
        client = GoogleDriveApiClient()
    else:
        client = LocalDriveMirror(args.local_dir)
    return GoogleDriveStorageAgent(client, folder_id=args.drive_folder_id), target


def main() -> int:
    parser = argparse.ArgumentParser(description="Build recommendations from stored daily market data")
    parser.add_argument("--dataset", default="market/daily-prices")
    parser.add_argument("--decision-time", required=True, help="ISO-8601 point-in-time for the recommendation")
    parser.add_argument("--trade-date", action="append", default=None, help="Optional partition date; repeat for multiple dates")
    parser.add_argument("--storage", choices=("auto", "drive", "local"), default="auto")
    parser.add_argument("--local-dir", default="./paper-live-data")
    parser.add_argument("--drive-folder-id", default=os.getenv("GOOGLE_DRIVE_DATA_FOLDER_ID"))
    parser.add_argument("--output-json", default=None, help="Write selected recommendations to JSON")
    args = parser.parse_args()

    try:
        decision = datetime.fromisoformat(args.decision_time.replace("Z", "+00:00"))
    except ValueError as exc:
        parser.error("--decision-time must be ISO-8601")
        raise AssertionError from exc

    dates = None
    if args.trade_date:
        try:
            dates = [date.fromisoformat(value).isoformat() for value in args.trade_date]
        except ValueError as exc:
            parser.error("--trade-date must be YYYY-MM-DD")
            raise AssertionError from exc

    storage, target = _storage(args)
    rows = storage.read_partitioned_jsonl(args.dataset, trade_dates=dates)
    if not rows:
        parser.error(f"no stored rows found for dataset: {args.dataset}")

    ranked, feature_manifest, recommendation_manifest = RecommendationPipeline(storage=storage).build_from_daily(
        rows, decision_time=decision.isoformat()
    )
    selected = [row for row in ranked if row.get("portfolio_selected")]
    payload = {
        "dataset": args.dataset,
        "storage": target,
        "decision_time": decision.isoformat(),
        "input_rows": len(rows),
        "feature_manifest": feature_manifest.__dict__,
        "recommendation_manifest": recommendation_manifest.__dict__,
        "selected": selected,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=list))
    if args.output_json:
        path = Path(args.output_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=list) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
