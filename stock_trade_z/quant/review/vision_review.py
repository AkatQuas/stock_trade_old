"""Unified VL chart review entry: config loading, reviewer factory, and session class."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from stock_trade_z.lib.paths import get_config_path, get_project_root
from stock_trade_z.quant.review.base_reviewer import BaseReviewer

_SUPPORTED_PROVIDERS = ("qwen", "gemini")


def _resolve_cfg_path(path_like: str | Path, base_dir: Path | None = None) -> Path:
    base = base_dir or get_project_root()
    p = Path(path_like)
    return p if p.is_absolute() else (base / p)


def _infer_provider(cfg_path: Path, raw: dict[str, Any]) -> str:
    if provider := raw.get("provider"):
        return str(provider)
    name = cfg_path.name.lower()
    if name.startswith("qwen"):
        return "qwen"
    if name.startswith("gemini"):
        return "gemini"
    raise ValueError(f"配置未指定 provider: {cfg_path}")


def _provider_entry(providers: list[Any], name: str) -> dict[str, Any]:
    for item in providers:
        if not isinstance(item, dict):
            continue
        if str(item.get("name", "")) == name:
            return {k: v for k, v in item.items() if k != "name"}
    available = [
        str(item.get("name"))
        for item in providers
        if isinstance(item, dict) and item.get("name") is not None
    ]
    raise ValueError(f"provider {name!r} 未在 providers 中定义，可用: {available}")


def _merge_review_config(
    raw: dict[str, Any],
    *,
    cfg_path: Path,
    provider_override: str | None = None,
) -> dict[str, Any]:
    provider = provider_override or _infer_provider(cfg_path, raw)

    providers = raw.get("providers")
    if not isinstance(providers, list):
        raise ValueError(f"配置缺少 providers 数组: {cfg_path}")

    meta_keys = {"provider", "providers"}
    shared = {k: v for k, v in raw.items() if k not in meta_keys}
    active = _provider_entry(providers, provider)
    return {**shared, **active, "provider": provider}


def _resolve_config_paths(cfg: dict[str, Any]) -> dict[str, Any]:
    for key in ("candidates", "kline_dir", "output_dir", "prompt_path"):
        if key in cfg:
            cfg[key] = _resolve_cfg_path(cfg[key])
    return cfg


def load_config(
    config_path: Path | None = None,
    *,
    provider: str | None = None,
) -> dict[str, Any]:
    """Load VL review config from vision_review.yaml (providers 数组 + 当前 provider)。"""
    cfg_path = config_path or get_config_path("vision_review.yaml")
    if not cfg_path.exists():
        raise FileNotFoundError(f"找不到 VL 复评配置文件: {cfg_path}")

    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    cfg = _merge_review_config(raw, cfg_path=cfg_path, provider_override=provider)
    return _resolve_config_paths(cfg)


def create_reviewer(config: dict[str, Any]) -> BaseReviewer:
    """Instantiate a VL reviewer from config['provider']."""
    provider = str(config["provider"])
    if provider == "qwen":
        from stock_trade_z.quant.review.qwen_review import QwenReviewer

        return QwenReviewer(config)
    if provider == "gemini":
        from stock_trade_z.quant.review.gemini_review import GeminiReviewer

        return GeminiReviewer(config)
    supported = ", ".join(_SUPPORTED_PROVIDERS)
    raise ValueError(f"未知 VL provider: {provider!r}，支持: {supported}")


class VisionReview:
    """VL 图表复评会话：绑定配置与 Reviewer，便于在 pipeline 中替换实现。"""

    def __init__(
        self,
        config_path: Path | None = None,
        *,
        config: dict[str, Any] | None = None,
        reviewer: BaseReviewer | None = None,
        provider: str | None = None,
    ):
        if reviewer is not None:
            self.reviewer = reviewer
            self.config = config or reviewer.config
            return

        self.config = config or load_config(config_path, provider=provider)
        self.reviewer = create_reviewer(self.config)

    @property
    def provider(self) -> str:
        return str(self.config["provider"])

    def run(self) -> dict | None:
        return self.reviewer.run()

    def suggestion_file(self, pick_date: str) -> Path:
        return Path(self.config["output_dir"]) / pick_date / "suggestion.json"


def run_review(
    config_path: Path | None = None,
    *,
    provider: str | None = None,
) -> dict | None:
    """Run VL chart review with default or custom config."""
    return VisionReview(config_path, provider=provider).run()
