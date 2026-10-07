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
    parser.add_argument("--max-pit-missing-timestamp", type=int, default=0, help="Fail when missing available_at rows exceed this count")
    parser.add_argument("--min-latest-candidates", type=int, default=1, help="Fail when latest PIT-eligible candidates are below this count")
    args = parser.parse_args()

    if args.max_pit_missing_timestamp < 0 or args.min_latest_candidates < 0:
        parser.error("quality gate thresholds must be non-negative")

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

    pipeline = RecommendationPipeline(storage=storage)
    ranked, feature_manifest, recommendation_manifest = pipeline.build_from_daily(
        rows, decision_time=decision.isoformat()
    )
    selected = [row for row in ranked if row.get("portfolio_selected")]
    quality = {
        "pit_eligible": pipeline.last_filter_stats.get("pit_eligible", 0),
        "pit_rejected": pipeline.last_filter_stats.get("pit_rejected", 0),
        "pit_missing_timestamp": pipeline.last_filter_stats.get("pit_missing_timestamp", 0),
        "pit_future_timestamp": pipeline.last_filter_stats.get("pit_future_timestamp", 0),
        "latest_candidates": pipeline.last_filter_stats.get("latest_candidates", 0),
        "selected_candidates": pipeline.last_filter_stats.get("selected_candidates", 0),
    }
    quality["gate_max_pit_missing_timestamp"] = args.max_pit_missing_timestamp
    quality["gate_min_latest_candidates"] = args.min_latest_candidates
    quality["gate_passed"] = (
        quality["pit_missing_timestamp"] <= args.max_pit_missing_timestamp
        and quality["latest_candidates"] >= args.min_latest_candidates
    )
    payload = {
        "dataset": args.dataset,
        "storage": target,
        "decision_time": decision.isoformat(),
        "input_rows": len(rows),
        "feature_manifest": feature_manifest.__dict__,
        "recommendation_manifest": recommendation_manifest.__dict__,
        "quality": quality,
        "selected": selected,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=list))
    if args.output_json:
        path = Path(args.output_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=list) + "\n", encoding="utf-8")
    if not quality["gate_passed"]:
        print(
            "recommendation quality gate failed: "
            f"missing_timestamp={quality['pit_missing_timestamp']} "
            f"(max {args.max_pit_missing_timestamp}), "
            f"latest_candidates={quality['latest_candidates']} "
            f"(min {args.min_latest_candidates})",
            flush=True,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
