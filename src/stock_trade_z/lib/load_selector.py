"""Load stock selection strategies from selector.config.json."""

from __future__ import annotations

from typing import Any

from .registry import load_registry


def load_selectors() -> dict[str, Any]:
    """Load all selectors: Z-style (`selectors`) + quant (`quant_selectors`)."""
    z_selectors = load_registry(
        "selector.config.json",
        list_key="selectors",
        module_path="stock_trade_z.lib.selector",
    )
    quant_selectors = load_registry(
        "selector.config.json",
        list_key="quant_selectors",
        module_path="stock_trade_z.lib.quant_selectors",
    )
    merged = z_selectors.copy()
    merged.update(quant_selectors)
    return merged
