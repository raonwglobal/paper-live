from __future__ import annotations

import pytest

from paper_live.operational_cli import _load_factory


def test_load_factory_rejects_invalid_reference():
    with pytest.raises(ValueError, match="module:callable"):
        _load_factory("invalid")


def test_load_factory_rejects_missing_callable():
    with pytest.raises(AttributeError):
        _load_factory("paper_live.operational_cli:not_a_factory")
