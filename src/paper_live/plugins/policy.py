from __future__ import annotations

class PluginModeDenied(PermissionError):
    pass

class PluginExecutionPolicy:
    """Central deny-by-default gate for plugin skills."""
    def __init__(self, allowed_modes: set[str] | None = None):
        self.allowed_modes = allowed_modes or {"PAPER_SANDBOX", "VIRTUAL_BACKTEST"}

    def check(self, mode: str) -> None:
        if mode not in self.allowed_modes:
            raise PluginModeDenied(f"plugin execution denied in mode: {mode}")

    def can_live(self) -> bool:
        return "REAL_LIVE" in self.allowed_modes
