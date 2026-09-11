import json

import pytest

from paper_live.brokers.credentials import CredentialParseError, parse_kb_credentials
from paper_live.brokers.kb import DEFAULT_BUY_ORDER_PATH, KbBrokerAdapter, KbCredentials


def test_kb_json_credentials_use_verified_buy_endpoint_default() -> None:
    credentials = parse_kb_credentials(json.dumps({"app_key": "key", "app_secret": "secret"}))

    assert credentials == KbCredentials("key", "secret", DEFAULT_BUY_ORDER_PATH)
    assert DEFAULT_BUY_ORDER_PATH == "/api/v1/ssam1802"


def test_kb_legacy_credentials_preserve_explicit_endpoint() -> None:
    credentials = parse_kb_credentials("key:secret:/api/v1/custom")

    assert credentials.order_path == "/api/v1/custom"


def test_kb_empty_credentials_are_rejected() -> None:
    with pytest.raises(CredentialParseError):
        parse_kb_credentials("")


def test_kb_submit_stays_blocked_without_pinned_order_schema() -> None:
    adapter = KbBrokerAdapter(KbCredentials("key", "secret"))

    with pytest.raises(NotImplementedError, match="official JSON API schema"):
        adapter.submit(None)  # type: ignore[arg-type]
