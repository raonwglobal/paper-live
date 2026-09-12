from pathlib import Path

import pytest

from paper_live.plugins.package_policy import PluginPackageError, validate_package


def test_manifest_required(tmp_path: Path):
    with pytest.raises(PluginPackageError):
        validate_package(tmp_path)


def test_shell_installer_is_rejected(tmp_path: Path):
    (tmp_path / "plugin.yaml").write_text("x: y")
    (tmp_path / "install.sh").write_text("echo unsafe")
    with pytest.raises(PluginPackageError):
        validate_package(tmp_path)


def test_git_metadata_is_rejected(tmp_path: Path):
    (tmp_path / "plugin.yaml").write_text("x: y")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("unsafe")
    with pytest.raises(PluginPackageError):
        validate_package(tmp_path)


def test_safe_package_is_accepted(tmp_path: Path):
    (tmp_path / "plugin.yaml").write_text("x: y")
    (tmp_path / "README.md").write_text("safe")
    (tmp_path / "skills").mkdir()
    (tmp_path / "skills" / "quote.py").write_text("print('protocol')")
    validate_package(tmp_path)
