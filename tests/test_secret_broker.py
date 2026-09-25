import pytest

from paper_live.plugins.secrets import SecretAccessDenied, SecretBroker


def test_only_allowlisted_secret_is_resolved():
    broker = SecretBroker({"API_KEY": "secret"})
    assert broker.resolve("API_KEY", {"API_KEY"}) == "secret"
    with pytest.raises(SecretAccessDenied):
        broker.resolve("API_KEY", set())
