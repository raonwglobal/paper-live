import pytest

from paper_live.plugins.sandbox import PluginSandbox, SandboxPolicy, SandboxViolation


def test_network_is_allow_listed():
    s = PluginSandbox(SandboxPolicy(network_hosts=("api.example.com",)))
    s.check_network("api.example.com")
    with pytest.raises(SandboxViolation):
        s.check_network("evil.example.com")


def test_filesystem_is_allow_listed():
    s = PluginSandbox(SandboxPolicy(readable_paths=("/plugin/data",), writable_paths=("/plugin/out",)))
    s.check_read("/plugin/data/a.json")
    s.check_write("/plugin/out/a.json")
    with pytest.raises(SandboxViolation):
        s.check_read("/etc/passwd")
    with pytest.raises(SandboxViolation):
        s.check_write("/tmp/x")


def test_shell_is_denied_by_default():
    with pytest.raises(SandboxViolation):
        PluginSandbox().check_shell()
