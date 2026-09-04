import pytest

from paper_live.plugins import PermissionPolicy, PluginManifest, PluginRegistry


def manifest(**kwargs):
    values = dict(
        id="demo-plugin", version="1.0.0", name="Demo", entrypoint="src/main.py", source_commit="abc", sha256="hash"
    )
    values.update(kwargs)
    return PluginManifest(**values)


def test_unverified_plugin_cannot_enable():
    r = PluginRegistry()
    r.add("https://github.com/example/demo", manifest())
    with pytest.raises(PermissionError):
        r.enable("demo-plugin")


def test_verified_plugin_can_enable():
    r = PluginRegistry()
    r.add("https://github.com/example/demo", manifest())
    r.verify("demo-plugin", "abc", "hash")
    assert r.enable("demo-plugin").enabled


def test_live_cannot_be_granted_by_manifest():
    # Validation is explicit (load/registry time), not dataclass construction.
    m = manifest(permissions=PermissionPolicy(allowed_modes=("REAL_LIVE",)))
    with pytest.raises(ValueError, match="REAL_LIVE"):
        m.validate()


def test_non_github_url_rejected():
    r = PluginRegistry()
    with pytest.raises(ValueError):
        r.add("http://evil.example/plugin", manifest())
