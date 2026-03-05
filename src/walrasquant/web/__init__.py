"""Public interface for strategy web integration."""

from __future__ import annotations

from .app import StrategyFastAPI, create_strategy_app
from .server import StrategyWebServer

__all__ = [
    "StrategyFastAPI",
    "StrategyWebServer",
    "create_strategy_app",
    "app",
]


def __getattr__(name: str) -> object:
    """Lazy-initialise the convenience ``app`` singleton on first access."""
    if name == "app":
        import sys

        module = sys.modules[__name__]
        instance = create_strategy_app()
        # Cache so subsequent attribute access is O(1)
        module.app = instance  # type: ignore[attr-defined]
        return instance
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
