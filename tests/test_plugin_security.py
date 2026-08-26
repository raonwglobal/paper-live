import pytest
from paper_live.plugins.loader import PluginSourceLoader, RepositorySource
from paper_live.plugins.security import PluginSecurityError, PluginSecurityValidator

def test_manifest_url_requires_github_https():
    loader = PluginSourceLoader()
    assert loader.manifest_url(RepositorySource("https://github.com/acme/demo")) == "https://raw.githubusercontent.com/acme/demo/main/plugin.yaml"
    with pytest.raises(PluginSecurityError):
        loader.manifest_url(RepositorySource("http://github.com/acme/demo"))
    with pytest.raises(PluginSecurityError):
        loader.manifest_url(RepositorySource("https://evil.example/acme/demo"))

def test_credentials_in_url_are_rejected():
    with pytest.raises(PluginSecurityError):
        PluginSecurityValidator().validate_source("https://user:secret@github.com/acme/demo")
