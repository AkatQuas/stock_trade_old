"""Gemini multimodal chart review for quant candidates."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import yaml
from google import genai
from google.genai import types

from stock_trade_z.lib.logger import get_logger
from stock_trade_z.lib.paths import get_config_path, get_project_root
from stock_trade_z.quant.review.base_reviewer import BaseReviewer

logger = get_logger("quant")

DEFAULT_CONFIG: dict[str, Any] = {
    "candidates": "data/candidates/candidates_latest.json",
    "kline_dir": "data/kline",
    "output_dir": "data/review",
    "prompt_path": "stock_trade_z/quant/review/prompt.md",
    "model": "gemini-2.0-flash",
    "request_delay": 5,
    "skip_existing": False,
    "suggest_min_score": 4.0,
}


def _resolve_cfg_path(path_like: str | Path, base_dir: Path | None = None) -> Path:
    base = base_dir or get_project_root()
    p = Path(path_like)
    return p if p.is_absolute() else (base / p)


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    cfg_path = config_path or get_config_path("gemini_review.yaml")
    if not cfg_path.exists():
        raise FileNotFoundError(f"找不到配置文件: {cfg_path}")

    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    cfg = {**DEFAULT_CONFIG, **raw}

    cfg["candidates"] = _resolve_cfg_path(cfg["candidates"])
    cfg["kline_dir"] = _resolve_cfg_path(cfg["kline_dir"])
    cfg["output_dir"] = _resolve_cfg_path(cfg["output_dir"])
    cfg["prompt_path"] = _resolve_cfg_path(cfg["prompt_path"])
    return cfg


class GeminiReviewer(BaseReviewer):
    def __init__(self, config: dict[str, Any]):
        super().__init__(config)

        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            logger.error("未找到环境变量 GEMINI_API_KEY")
            sys.exit(1)

        self.client = genai.Client(api_key=api_key)

    @staticmethod
    def image_to_part(path: Path) -> types.Part:
        suffix = path.suffix.lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
        mime_type = mime_map.get(suffix, "image/jpeg")
        data = path.read_bytes()
        return types.Part.from_bytes(data=data, mime_type=mime_type)

    def review_stock(self, code: str, day_chart: Path, prompt: str) -> dict:
        user_text = (
            f"股票代码：{code}\n\n"
            "以下是该股票的 **日线图**，请按照系统提示中的框架进行分析，"
            "并严格按照要求输出 JSON。"
        )

        parts: list[types.Part] = [
            types.Part.from_text(text="【日线图】"),
            self.image_to_part(day_chart),
            types.Part.from_text(text=user_text),
        ]

        response = self.client.models.generate_content(
            model=self.config.get("model", "gemini-2.0-flash"),
            contents=[types.Content(role="user", parts=parts)],
            config=types.GenerateContentConfig(
                system_instruction=prompt,
                temperature=0.2,
            ),
        )

        response_text = response.text
        if response_text is None:
            raise RuntimeError(f"Gemini 返回空响应，无法解析 JSON（code={code}）")

        result = self.extract_json(response_text)
        result["code"] = code
        return result


def run_review(config_path: Path | None = None) -> dict | None:
    config = load_config(config_path)
    reviewer = GeminiReviewer(config)
    return reviewer.run()


def main() -> None:
    parser = argparse.ArgumentParser(description="Gemini 图表复评")
    parser.add_argument("--config", default=None, help="gemini_review.yaml 路径")
    args = parser.parse_args()

    cfg_path = Path(args.config) if args.config else None
    run_review(cfg_path)


if __name__ == "__main__":
    main()
