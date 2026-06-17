"""Gemini multimodal chart review for quant candidates."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from stock_trade_z.lib.logger import get_logger
from stock_trade_z.quant.review.base_reviewer import BaseReviewer

logger = get_logger("quant")


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
        user_text = self.build_review_user_text(code)

        parts: list[types.Part] = [
            types.Part.from_text(text="【日线图】"),
            self.image_to_part(day_chart),
            types.Part.from_text(text=user_text),
        ]

        response = self.client.models.generate_content(
            model=self.config["model"],
            contents=[types.Content(role="user", parts=parts)],
            config=types.GenerateContentConfig(
                system_instruction=prompt,
                temperature=self.config["temperature"],
            ),
        )

        response_text = response.text
        if response_text is None:
            raise RuntimeError(f"Gemini 返回空响应（code={code}）")

        result = self.parse_review_text(response_text)
        result["code"] = code
        return result


def main() -> None:
    from stock_trade_z.quant.review.vision_review import VisionReview

    parser = argparse.ArgumentParser(description="Gemini VL 图表复评")
    parser.add_argument("--config", default=None, help="复评 YAML 路径")
    args = parser.parse_args()

    cfg_path = Path(args.config) if args.config else None
    VisionReview(cfg_path, provider="gemini" if cfg_path is None else None).run()


if __name__ == "__main__":
    main()
