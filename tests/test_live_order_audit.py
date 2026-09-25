from decimal import Decimal

from paper_live.execution import Fill, OrderSide
from paper_live.execution_audit import ExecutionAuditTrail
from paper_live.trade_facade import OrderIntent, RiskAssessment


def test_zero_quantity_live_ack_is_not_recorded_as_fill():
    audit = ExecutionAuditTrail()
    submission = audit.create_submission(
        intent=OrderIntent(symbol="005930", side="BUY", quantity=Decimal("10"), broker="toss"),
        reference_price=Decimal("70000"),
        risk=RiskAssessment(True, "PASS"),
        broker="toss",
        run_manifest_id="run-live-1",
    )

    updated = audit.record_fill(
        submission,
        Fill(
            order_id="live-order-1",
            symbol="005930",
            side=OrderSide.BUY,
            quantity=Decimal("0"),
            price=Decimal("70000"),
            fee=Decimal("0"),
            tax=Decimal("0"),
            status="ACCEPTED",
        ),
    )

    assert updated.status == "ACCEPTED"
    assert updated.broker_order_id == "live-order-1"
    assert updated.fill_quantity is None
    assert updated.fill_price is None
    assert updated.fee is None
    assert updated.tax is None


def test_real_fill_still_records_execution_fields():
    audit = ExecutionAuditTrail()
    submission = audit.create_submission(
        intent=OrderIntent(symbol="005930", side="BUY", quantity=Decimal("10"), broker="toss"),
        reference_price=Decimal("70000"),
        risk=RiskAssessment(True, "PASS"),
        broker="toss",
    )

    updated = audit.record_fill(
        submission,
        Fill(
            order_id="paper-order-1",
            symbol="005930",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            price=Decimal("70100"),
            fee=Decimal("210"),
            tax=Decimal("0"),
            status="FILLED",
        ),
    )

    assert updated.status == "FILLED"
    assert updated.broker_order_id == "paper-order-1"
    assert updated.fill_quantity == "10"
    assert updated.fill_price == "70100"
    assert updated.fee == "210"
