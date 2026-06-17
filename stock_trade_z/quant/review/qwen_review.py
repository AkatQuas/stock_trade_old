"""Qwen multimodal chart review for quant candidates (DashScope OpenAI-compatible)."""

from __future__ import annotations

import argparse
import base64
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from stock_trade_z.lib.logger import get_logger
from stock_trade_z.lib.paths import get_project_root
from stock_trade_z.quant.review.base_reviewer import BaseReviewer

logger = get_logger("quant")


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
            base_url=config["base_url"],
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
        enable_thinking = bool(self.config["enable_thinking"])
        extra_body: dict[str, Any] = {"enable_thinking": enable_thinking}
        if enable_thinking:
            extra_body["thinking_budget"] = self.config["thinking_budget"]
        if self.config.get("vl_high_resolution_images"):
            extra_body["vl_high_resolution_images"] = True
        return extra_body

    def _stream_completion(self, messages: list[dict[str, Any]]) -> str:
        create_kwargs: dict[str, Any] = {
            "model": self.config["model"],
            "messages": messages,
            "temperature": self.config["temperature"],
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
        user_text = self.build_review_user_text(code)

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
        result = self.parse_review_text(response_text)
        result["code"] = code
        return result


def main() -> None:
    from stock_trade_z.quant.review.vision_review import VisionReview

    parser = argparse.ArgumentParser(description="Qwen VL 图表复评")
    parser.add_argument("--config", default=None, help="复评 YAML 路径（默认 vision_review.yaml）")
    args = parser.parse_args()

    cfg_path = Path(args.config) if args.config else None
    VisionReview(cfg_path, provider="qwen" if cfg_path is None else None).run()


if __name__ == "__main__":
    main()
