from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import hashlib
import shutil
import subprocess
import tempfile
from .loader import RepositorySource, PluginSourceLoader
from .manifest import PluginManifest
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
    """Installs pinned repositories only after validation.

    Execution is intentionally separate: installation never imports plugin code.
    """
    def __init__(self, root: str = ".paper-live/plugins", loader: PluginSourceLoader | None = None,
                 validator: PluginSecurityValidator | None = None):
        self.root = Path(root)
        self.loader = loader or PluginSourceLoader()
        self.validator = validator or PluginSecurityValidator()

    def _archive_hash(self, directory: Path) -> str:
        h = hashlib.sha256()
        for p in sorted(x for x in directory.rglob("*") if x.is_file()):
            h.update(str(p.relative_to(directory)).encode())
            h.update(p.read_bytes())
        return h.hexdigest()

    def install(self, source: RepositorySource, plugin_id: str, version: str, commit: str) -> InstalledPlugin:
        if not commit or len(commit) < 7:
            raise PluginInstallError("immutable commit is required")
        self.validator.validate_source(source.url)
        manifest_text = self.loader.fetch_manifest(RepositorySource(source.url, commit))
        if not manifest_text.strip():
            raise PluginInstallError("empty plugin manifest")
        with tempfile.TemporaryDirectory(prefix="paper-live-plugin-") as td:
            dest = Path(td) / "repo"
            subprocess.run(["git", "clone", "--depth", "1", source.url, str(dest)], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            subprocess.run(["git", "-C", str(dest), "fetch", "--depth", "1", "origin", commit], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            subprocess.run(["git", "-C", str(dest), "checkout", "--detach", commit], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            digest = self._archive_hash(dest)
            target = self.root / plugin_id / version / commit
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(dest, target)
        return InstalledPlugin(plugin_id, version, source.url, commit, digest, str(target))
