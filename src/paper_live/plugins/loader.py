from __future__ import annotations
from dataclasses import dataclass
from urllib.request import Request, urlopen
from .security import PluginSecurityValidator

@dataclass(frozen=True)
class RepositorySource:
    url: str
    ref: str = "main"

class PluginSourceLoader:
    """Fetches only manifest metadata; it never executes repository code."""
    def __init__(self, validator: PluginSecurityValidator | None = None, timeout: float = 10.0):
        self.validator = validator or PluginSecurityValidator()
        self.timeout = timeout

    def manifest_url(self, source: RepositorySource) -> str:
        self.validator.validate_source(source.url)
        parts = source.url.rstrip("/").split("/")
        if len(parts) < 5 or parts[2] != "github.com":
            raise ValueError("expected github.com owner/repository URL")
        owner, repo = parts[3], parts[4].removesuffix(".git")
        if not owner or not repo:
            raise ValueError("invalid GitHub repository")
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{source.ref}/plugin.yaml"

    def fetch_manifest(self, source: RepositorySource) -> str:
        url = self.manifest_url(source)
        request = Request(url, headers={"User-Agent": "paper-live-plugin-loader/1.0"})
        with urlopen(request, timeout=self.timeout) as response:
            return response.read().decode("utf-8")
