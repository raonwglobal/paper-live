from decimal import Decimal

import pytest

from paper_live.position_sizing import PositionSizer


def test_size_respects_risk_and_notional_caps():
    s = PositionSizer()
    q = s.size(Decimal("100000"), Decimal("100"), Decimal("10"))
    assert q == Decimal("100.000000")


def test_size_is_limited_by_notional_cap():
    s = PositionSizer()
    q = s.size(Decimal("100000"), Decimal("100"), Decimal("1"))
    assert q == Decimal("200.000000")


def test_invalid_sizing_inputs_rejected():
    with pytest.raises(ValueError):
        PositionSizer().size(Decimal("0"), Decimal("100"), Decimal("10"))
