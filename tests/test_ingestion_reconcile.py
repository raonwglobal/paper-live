from paper_live.ingestion_reconcile import RecoveryReconciler
from paper_live.market_dataset import DailyPriceRecord


def row(
    symbol: str,
    trade_date: str,
    *,
    source: str = "source",
    available_at: str = "2026-08-29T00:00:00+00:00",
):
    return DailyPriceRecord(
        symbol,
        "KRX",
        trade_date,
        1,
        1,
        1,
        100,
        10,
        source=source,
        available_at=available_at,
    )


def test_reconciliation_adds_only_missing_recovery_keys():
    canonical = (row("A", "2026-08-28"),)
    recovery = (
        row("A", "2026-08-28", source="retry"),
        row("B", "2026-08-28", source="retry"),
    )

    merged, report = RecoveryReconciler().merge(canonical, recovery)

    assert [item.symbol for item in merged] == ["A", "B"]
    assert merged[0].source == "source"
    assert report.added_rows == 1
    assert report.duplicate_recovery_rows == 1
    assert report.output_rows == 2


def test_reconciliation_is_deterministic_for_recovery_order():
    recovery = [
        row("B", "2026-08-28", available_at="2026-08-29T02:00:00+00:00"),
        row("A", "2026-08-29", available_at="2026-08-29T01:00:00+00:00"),
    ]

    first, _ = RecoveryReconciler().merge((), recovery)
    second, _ = RecoveryReconciler().merge((), reversed(recovery))

    assert [item.as_row() for item in first] == [item.as_row() for item in second]


def test_reconciliation_preserves_canonical_duplicate_key():
    canonical = (
        row("A", "2026-08-28", source="first"),
        row("A", "2026-08-28", source="second"),
    )

    merged, report = RecoveryReconciler().merge(canonical, ())

    assert len(merged) == 1
    assert merged[0].source == "first"
    assert report.canonical_rows == 2
