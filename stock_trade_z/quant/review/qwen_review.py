"""Qwen multimodal chart review for quant candidates (DashScope OpenAI-compatible)."""

from __future__ import annotations

import argparse
import base64
import os
import sys
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from openai import OpenAI

from stock_trade_z.lib.logger import get_logger
from stock_trade_z.lib.paths import get_config_path, get_project_root
from stock_trade_z.quant.review.base_reviewer import BaseReviewer

logger = get_logger("quant")

DEFAULT_CONFIG: dict[str, Any] = {
    "candidates": "data/candidates/candidates_latest.json",
    "kline_dir": "data/kline",
    "output_dir": "data/review",
    "prompt_path": "stock_trade_z/quant/review/prompt.md",
    "model": "qwen3.7-plus",
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "request_delay": 5,
    "skip_existing": False,
    "suggest_min_score": 4.0,
    "enable_thinking": True,
    "thinking_budget": 81920,
    # Qwen3.7 思考模式默认 temperature=0.6（见 qwen.md）
    "temperature": 0.6,
    "response_format": "json_object",
    "max_completion_tokens": None,
    "vl_high_resolution_images": True,
}


def _resolve_cfg_path(path_like: str | Path, base_dir: Path | None = None) -> Path:
    base = base_dir or get_project_root()
    p = Path(path_like)
    return p if p.is_absolute() else (base / p)


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    cfg_path = config_path or get_config_path("qwen_review.yaml")
    if not cfg_path.exists():
        raise FileNotFoundError(f"找不到配置文件: {cfg_path}")

    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    cfg = {**DEFAULT_CONFIG, **raw}

    cfg["candidates"] = _resolve_cfg_path(cfg["candidates"])
    cfg["kline_dir"] = _resolve_cfg_path(cfg["kline_dir"])
    cfg["output_dir"] = _resolve_cfg_path(cfg["output_dir"])
    cfg["prompt_path"] = _resolve_cfg_path(cfg["prompt_path"])
    return cfg


class QwenReviewer(BaseReviewer):
    def __init__(self, config: dict[str, Any]):
        super().__init__(config)

        load_dotenv(get_project_root() / ".env")

        api_key = os.environ.get("DASHSCOPE_API_KEY", "")
        if not api_key:
            logger.error("未找到环境变量 DASHSCOPE_API_KEY")
            sys.exit(1)

        self.client = OpenAI(
            api_key=api_key,
            base_url=config.get("base_url", DEFAULT_CONFIG["base_url"]),
        )

    @staticmethod
    def _b64_data_url(path: Path) -> str:
        suffix = path.suffix.lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
        mime = mime_map.get(suffix, "image/jpeg")
        b64 = base64.standard_b64encode(path.read_bytes()).decode()
        return f"data:{mime};base64,{b64}"

    @staticmethod
    def _delta_reasoning_content(delta: Any) -> str | None:
        reasoning = getattr(delta, "reasoning_content", None)
        if reasoning is None:
            reasoning = (getattr(delta, "model_extra", None) or {}).get("reasoning_content")
        return reasoning

    @staticmethod
    def _collect_stream_answer(chunks: Any) -> str:
        """拼接流式最终回复，忽略 reasoning_content 思维链增量。"""
        answer_content = ""
        for chunk in chunks:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if QwenReviewer._delta_reasoning_content(delta) is not None:
                continue
            if delta.content:
                answer_content += delta.content
        return answer_content

    def _build_extra_body(self) -> dict[str, Any]:
        enable_thinking = bool(self.config.get("enable_thinking", True))
        extra_body: dict[str, Any] = {"enable_thinking": enable_thinking}
        if enable_thinking:
            extra_body["thinking_budget"] = self.config.get(
                "thinking_budget", DEFAULT_CONFIG["thinking_budget"]
            )
        if self.config.get("vl_high_resolution_images", True):
            extra_body["vl_high_resolution_images"] = True
        return extra_body

    def _stream_completion(self, messages: list[dict[str, Any]]) -> str:
        create_kwargs: dict[str, Any] = {
            "model": self.config.get("model", "qwen3.7-plus"),
            "messages": messages,
            "temperature": self.config.get("temperature", DEFAULT_CONFIG["temperature"]),
            "stream": True,
            "extra_body": self._build_extra_body(),
        }
        if self.config.get("response_format") == "json_object":
            create_kwargs["response_format"] = {"type": "json_object"}
        max_completion_tokens = self.config.get("max_completion_tokens")
        if max_completion_tokens is not None:
            create_kwargs["max_completion_tokens"] = max_completion_tokens

        completion = self.client.chat.completions.create(**create_kwargs)
        return self._collect_stream_answer(completion)

    def review_stock(self, code: str, day_chart: Path, prompt: str) -> dict:
        user_text = (
            f"股票代码：{code}\n\n"
            "以下是该股票的 **日线图**，请按照系统提示中的框架进行分析，"
            "并严格按照要求输出 JSON。"
        )

        messages = [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "【日线图】"},
                    {
                        "type": "image_url",
                        "image_url": {"url": self._b64_data_url(day_chart)},
                    },
                    {"type": "text", "text": user_text},
                ],
            },
        ]

        response_text = self._stream_completion(messages)
        if not response_text.strip():
            raise RuntimeError(f"Qwen 返回空响应，无法解析 JSON（code={code}）")

        result = self.extract_json(response_text)
        result["code"] = code
        return result


def run_review(config_path: Path | None = None) -> dict | None:
    config = load_config(config_path)
    reviewer = QwenReviewer(config)
    return reviewer.run()


def main() -> None:
    parser = argparse.ArgumentParser(description="Qwen 图表复评")
    parser.add_argument("--config", default=None, help="qwen_review.yaml 路径")
    args = parser.parse_args()

    cfg_path = Path(args.config) if args.config else None
    run_review(cfg_path)


if __name__ == "__main__":
    main()
