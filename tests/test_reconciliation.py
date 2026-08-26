from decimal import Decimal
from paper_live.order_lifecycle import OrderLifecycle, OrderRecord
from paper_live.reconciliation import OrderReconciler

def test_reconciliation_detects_status_and_fill_drift():
    lifecycle = OrderLifecycle()
    lifecycle.submit(OrderRecord("r1", "ABC", "BUY", Decimal("10")))
    lifecycle.fill("r1", Decimal("4"))
    issues = OrderReconciler(lifecycle).compare([
        {"client_order_id": "r1", "status": "FILLED", "filled_quantity": "10"}
    ])
    assert {i.kind for i in issues} == {"STATUS_DRIFT", "FILL_DRIFT"}

def test_reconciliation_detects_unknown_order():
    issues = OrderReconciler(lifecycle).compare([{ "client_order_id": "missing", "status": "NEW" }]) if False else OrderReconciler(OrderLifecycle()).compare([{ "client_order_id": "missing", "status": "NEW" }])
    assert issues[0].kind == "MISSING_LOCAL"
