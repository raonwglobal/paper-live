from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .loader import PluginSourceLoader, RepositorySource
from .manifest import load_manifest
from .package_policy import PluginPackageError, validate_package
from .security import PluginSecurityValidator


class PluginInstallError(RuntimeError):
    pass


@dataclass(frozen=True)
class InstalledPlugin:
    plugin_id: str
    version: str
    source: str
    commit: str
    artifact_sha256: str
    path: str


class PluginInstaller:
    """Install a pinned repository without executing plugin code or build scripts."""

    def __init__(
        self,
        root: str = ".paper-live/plugins",
        loader: PluginSourceLoader | None = None,
        validator: PluginSecurityValidator | None = None,
    ):
        self.root = Path(root)
        self.loader = loader or PluginSourceLoader()
        self.validator = validator or PluginSecurityValidator()

    @staticmethod
    def _payload_hash(directory: Path) -> str:
        h = hashlib.sha256()
        for p in sorted(
            x for x in directory.rglob("*") if x.is_file() and ".git" not in x.parts and x.name != "plugin.yaml"
        ):
            h.update(str(p.relative_to(directory)).encode())
            h.update(b"\0")
            h.update(p.read_bytes())
        return h.hexdigest()

    def install(self, source: RepositorySource, plugin_id: str, version: str, commit: str) -> InstalledPlugin:
        if not commit or len(commit) < 7:
            raise PluginInstallError("immutable commit is required")
        self.validator.validate_source(source.url)
        with tempfile.TemporaryDirectory(prefix="paper-live-plugin-") as td:
            dest = Path(td) / "repo"
            try:
                subprocess.run(
                    ["git", "clone", "--no-checkout", "--depth", "1", source.url, str(dest)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                subprocess.run(
                    ["git", "-C", str(dest), "fetch", "--depth", "1", "origin", commit],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                resolved = subprocess.check_output(
                    ["git", "-C", str(dest), "rev-parse", "FETCH_HEAD"], text=True
                ).strip()
                if resolved != commit and not resolved.startswith(commit):
                    raise PluginInstallError("requested commit could not be resolved exactly")
                subprocess.run(
                    ["git", "-C", str(dest), "checkout", "--detach", resolved],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            except (subprocess.CalledProcessError, OSError) as exc:
                raise PluginInstallError("git repository retrieval failed") from exc
            manifest_path = dest / "plugin.yaml"
            if not manifest_path.is_file():
                raise PluginInstallError("plugin.yaml is required")
            import yaml

            manifest = load_manifest(yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {})
            if manifest.id != plugin_id or manifest.version != version:
                raise PluginInstallError("manifest identity/version mismatch")
            if manifest.source_commit and manifest.source_commit != resolved:
                raise PluginInstallError("manifest source commit mismatch")
            self.validator.validate_manifest(manifest)
            try:
                validate_package(dest)
            except PluginPackageError as exc:
                raise PluginInstallError(str(exc)) from exc
            digest = self._payload_hash(dest)
            if manifest.sha256 and manifest.sha256 != digest:
                raise PluginInstallError("artifact SHA-256 mismatch")
            target = self.root / plugin_id / version / resolved
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(dest, target, ignore=shutil.ignore_patterns(".git"))
        return InstalledPlugin(plugin_id, version, source.url, resolved, digest, str(target))
