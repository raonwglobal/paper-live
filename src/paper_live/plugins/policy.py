from __future__ import annotations


class PluginModeDenied(PermissionError):
    pass


class PluginExecutionPolicy:
    """Central deny-by-default gate for plugin skills.

    Plugin execution is deliberately limited to paper/backtest. REAL_LIVE is
    owned by the core broker/risk/approval path and cannot be enabled by a
    plugin policy instance.
    """

    SAFE_MODES = frozenset({"PAPER_SANDBOX", "VIRTUAL_BACKTEST"})

    def __init__(self, allowed_modes: set[str] | None = None):
        requested = set(allowed_modes) if allowed_modes is not None else set(self.SAFE_MODES)
        if "REAL_LIVE" in requested:
            raise PluginModeDenied("REAL_LIVE is not a valid plugin execution mode")
        self.allowed_modes = requested & set(self.SAFE_MODES)

    def check(self, mode: str) -> None:
        if mode not in self.allowed_modes:
            raise PluginModeDenied(f"plugin execution denied in mode: {mode}")

    def can_live(self) -> bool:
        return False
