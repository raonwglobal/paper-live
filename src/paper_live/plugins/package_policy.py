from __future__ import annotations

from pathlib import Path


class PluginPackageError(ValueError):
    pass


ALLOWED_ROOT_FILES = {"plugin.yaml", "README.md", "LICENSE", "pyproject.toml", "requirements.lock"}
BLOCKED_FILES = {"Dockerfile", "Makefile", "install.sh", "setup.py", "package.json", ".env"}
BLOCKED_SUFFIXES = {".pem", ".key", ".crt", ".p12", ".pfx"}


def validate_package(root: Path) -> None:
    if not root.is_dir():
        raise PluginPackageError("plugin package directory does not exist")
    manifest = root / "plugin.yaml"
    if not manifest.is_file():
        raise PluginPackageError("plugin.yaml is required")
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(part in {".git", ".github", ".ssh", "node_modules", "__pycache__"} for part in rel.parts):
            raise PluginPackageError(f"forbidden package path: {rel}")
        if p.name in BLOCKED_FILES or p.suffix.lower() in BLOCKED_SUFFIXES:
            raise PluginPackageError(f"forbidden package file: {rel}")
        if len(p.read_bytes()) > 5 * 1024 * 1024:
            raise PluginPackageError(f"package file too large: {rel}")
    for p in root.iterdir():
        if p.is_file() and p.name not in ALLOWED_ROOT_FILES:
            # source files are allowed only below src/ or skills/
            if p.name != "plugin.yaml":
                raise PluginPackageError(f"unexpected root file: {p.name}")
