import pytest
from paper_live.plugins.loader import PluginSourceLoader, RepositorySource
from paper_live.plugins.manifest import PermissionPolicy, PluginManifest
from paper_live.plugins.policy import PluginExecutionPolicy, PluginModeDenied
from paper_live.plugins.security import PluginSecurityError, PluginSecurityValidator

def test_manifest_url_requires_github_https():
    loader = PluginSourceLoader()
    assert loader.manifest_url(RepositorySource("https://github.com/acme/demo")) == "https://raw.githubusercontent.com/acme/demo/main/plugin.yaml"
    with pytest.raises(PluginSecurityError): loader.manifest_url(RepositorySource("http://github.com/acme/demo"))
    with pytest.raises(PluginSecurityError): loader.manifest_url(RepositorySource("https://evil.example/acme/demo"))

def test_credentials_in_url_are_rejected():
    with pytest.raises(PluginSecurityError): PluginSecurityValidator().validate_source("https://user:secret@github.com/acme/demo")

def test_manifest_shell_permission_is_rejected():
    manifest = PluginManifest("demo-plugin", "1.0", "Demo", "src/main.py", permissions=PermissionPolicy(shell=True))
    with pytest.raises(PluginSecurityError): PluginSecurityValidator().validate_manifest(manifest)

def test_manifest_live_permission_is_rejected():
    manifest = PluginManifest("demo-plugin", "1.0", "Demo", "src/main.py", permissions=PermissionPolicy(allowed_modes=("REAL_LIVE",)))
    with pytest.raises(ValueError): manifest.validate()

def test_plugin_policy_cannot_enable_live():
    with pytest.raises(PluginModeDenied): PluginExecutionPolicy({"REAL_LIVE"})
    assert PluginExecutionPolicy().can_live() is False
