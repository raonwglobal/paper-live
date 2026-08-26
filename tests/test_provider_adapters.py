import pytest
from paper_live.provider_adapters import ProviderConfig, DartAdapter, SecEdgarAdapter, OpenBBAdapter

def test_provider_requires_base_url():
    with pytest.raises(ValueError):
        DartAdapter(ProviderConfig(""))

def test_provider_url_and_auth_contract(monkeypatch):
    seen = {}
    def fake(url, headers=None, timeout=10):
        seen.update(url=url, headers=headers, timeout=timeout)
        return {"ok": True}
    monkeypatch.setattr("paper_live.provider_adapters.fetch_json", fake)
    result = SecEdgarAdapter(ProviderConfig("https://example.test", "secret", 3)).get("filings")
    assert result == {"ok": True}
    assert seen["url"] == "https://example.test/filings"
    assert seen["headers"]["Authorization"] == "Bearer secret"
    assert seen["timeout"] == 3

def test_openbb_adapter_is_provider_contract():
    assert OpenBBAdapter(ProviderConfig("https://example.test")).config.base_url == "https://example.test"
