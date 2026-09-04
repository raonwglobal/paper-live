from decimal import Decimal

import pytest

from paper_live.order_lifecycle import OrderLifecycle, OrderRecord, OrderStatus


def test_duplicate_submit_is_idempotent():
    lifecycle = OrderLifecycle()
    order = OrderRecord("c1", "ABC", "BUY", Decimal("10"))
    assert lifecycle.submit(order) == order
    assert lifecycle.submit(order) == order


def test_partial_fill_then_cancel():
    lifecycle = OrderLifecycle()
    lifecycle.submit(OrderRecord("c2", "ABC", "BUY", Decimal("10")))
    partial = lifecycle.fill("c2", Decimal("4"))
    assert partial.status is OrderStatus.PARTIALLY_FILLED
    canceled = lifecycle.cancel("c2")
    assert canceled.status is OrderStatus.CANCELED
    assert canceled.filled_quantity == Decimal("4")


def test_duplicate_id_with_different_order_rejected():
    lifecycle = OrderLifecycle()
    lifecycle.submit(OrderRecord("c3", "ABC", "BUY", Decimal("10")))
    with pytest.raises(ValueError):
        lifecycle.submit(OrderRecord("c3", "XYZ", "BUY", Decimal("10")))
