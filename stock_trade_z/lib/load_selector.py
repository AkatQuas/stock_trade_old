"""Load stock selection strategies from selector.config.json."""

from __future__ import annotations

from typing import Any

from .registry import load_registry


def load_selectors() -> dict[str, Any]:
    """Load all selectors from selector.config.json (`selectors` list)."""
    return load_registry(
        "selector.config.json",
        list_key="selectors",
        module_path="stock_trade_z.lib.selector",
    )
