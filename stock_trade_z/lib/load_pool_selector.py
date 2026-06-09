"""Load pool selectors from pool_selector.config.json."""

from __future__ import annotations

import importlib
from typing import Any

from .paths import get_config_path
from .registry import load_json_list


def load_pool_selectors() -> dict[str, Any]:
    cfg_path = get_config_path("pool_selector.config.json")
    entries = load_json_list(cfg_path, "pool_selectors")
    module = importlib.import_module("stock_trade_z.lib.pool_selectors")
    result: dict[str, Any] = {}

    for cfg in entries:
        if cfg.get("activate") is False:
            continue
        cls_name = cfg.get("class")
        if not cls_name:
            continue
        cls = getattr(module, cls_name)
        params = dict(cfg.get("params") or {})
        pool = cfg.get("pool")
        if pool and "pool" not in params:
            params["pool"] = pool
        alias = cfg.get("alias", cls_name)
        result[alias] = cls(**params)

    return result
