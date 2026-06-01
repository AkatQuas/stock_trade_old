"""Load risk detectors from risk.config.json."""

from __future__ import annotations

from typing import Any

from .registry import load_registry


def load_risk_selectors() -> dict[str, Any]:
    return load_registry(
        "risk.config.json",
        list_key="risk_selectors",
        module_path="stock_trade_z.lib.risk_selectors",
    )
