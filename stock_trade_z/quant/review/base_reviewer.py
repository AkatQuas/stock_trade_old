"""Base architecture for Gemini chart review."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from stock_trade_z.lib.logger import get_logger

logger = get_logger("quant")


class BaseReviewer:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.prompt = self.load_prompt(Path(config["prompt_path"]))
        self.kline_dir = Path(config["kline_dir"])
        self.output_dir = Path(config["output_dir"])

    @staticmethod
    def load_prompt(prompt_path: Path) -> str:
        return prompt_path.read_text(encoding="utf-8")

    @staticmethod
    def load_candidates(path: Path) -> dict:
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def find_chart_images(self, pick_date: str, code: str) -> Path | None:
        date_dir = self.kline_dir / pick_date
        day_chart = date_dir / f"{code}_day.jpg"
        if not day_chart.exists():
            day_chart_png = date_dir / f"{code}_day.png"
            day_chart = day_chart_png if day_chart_png.exists() else None
        return day_chart

    @staticmethod
    def extract_json(text: str) -> dict:
        code_block = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if code_block:
            text = code_block.group(1)
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError(f"未能在模型输出中找到 JSON 对象:\n{text}")
        return json.loads(text[start:end])

    def review_stock(self, code: str, day_chart: Path, prompt: str) -> dict:
        raise NotImplementedError("子类必须实现 review_stock 方法")

    def generate_suggestion(
        self, pick_date: str, all_results: list[dict], min_score: float
    ) -> dict:
        passed = [r for r in all_results if r.get("total_score", 0) >= min_score]
        excluded = [r["code"] for r in all_results if r.get("total_score", 0) < min_score]

        passed.sort(key=lambda r: r.get("total_score", 0), reverse=True)

        recommendations = [
            {
                "rank": i + 1,
                "code": r["code"],
                "verdict": r.get("verdict", ""),
                "total_score": r.get("total_score", 0),
                "signal_type": r.get("signal_type", ""),
                "comment": r.get("comment", ""),
            }
            for i, r in enumerate(passed)
        ]

        return {
            "date": pick_date,
            "min_score_threshold": min_score,
            "total_reviewed": len(all_results),
            "recommendations": recommendations,
            "excluded": excluded,
        }

    def run(self) -> dict | None:
        candidates_data = self.load_candidates(Path(self.config["candidates"]))
        pick_date: str = candidates_data["pick_date"]
        candidates: list[dict] = candidates_data["candidates"]
        logger.info("pick_date=%s，候选股票数=%d", pick_date, len(candidates))

        if not candidates:
            logger.info("无候选股票，跳过 Gemini 复评")
            return None

        out_dir = self.output_dir / pick_date
        out_dir.mkdir(parents=True, exist_ok=True)

        all_results: list[dict] = []
        failed_codes: list[str] = []

        for i, candidate in enumerate(candidates, 1):
            code: str = candidate["code"]
            out_file = out_dir / f"{code}.json"

            if self.config.get("skip_existing", False) and out_file.exists():
                logger.info("[%d/%d] %s — 已存在，跳过", i, len(candidates), code)
                result = json.loads(out_file.read_text(encoding="utf-8"))
                all_results.append(result)
                continue

            day_chart = self.find_chart_images(pick_date, code)
            if day_chart is None:
                logger.warning("[%d/%d] %s — 缺少日线图，跳过", i, len(candidates), code)
                failed_codes.append(code)
                continue

            logger.info("[%d/%d] %s — 正在分析 ...", i, len(candidates), code)

            try:
                result = self.review_stock(code=code, day_chart=day_chart, prompt=self.prompt)
                out_file.write_text(
                    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                all_results.append(result)
                logger.info(
                    "完成 — verdict=%s, score=%s",
                    result.get("verdict", "?"),
                    result.get("total_score", "?"),
                )
            except Exception as e:
                logger.error("失败 — %s", e)
                failed_codes.append(code)

            if i < len(candidates):
                time.sleep(self.config.get("request_delay", 5))

        logger.info("评分完成: 成功 %d 支，失败/跳过 %d 支", len(all_results), len(failed_codes))
        if failed_codes:
            logger.warning("未处理股票: %s", failed_codes)

        if not all_results:
            logger.error("没有可用的评分结果，跳过汇总")
            return None

        logger.info("正在生成汇总推荐建议 ...")
        min_score = self.config.get("suggest_min_score", 4.0)
        suggestion = self.generate_suggestion(
            pick_date=pick_date,
            all_results=all_results,
            min_score=min_score,
        )
        suggestion_file = out_dir / "suggestion.json"
        suggestion_file.write_text(
            json.dumps(suggestion, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info(
            "汇总推荐已写入: %s (推荐 %d 只, score≥%.1f)",
            suggestion_file,
            len(suggestion["recommendations"]),
            min_score,
        )
        return suggestion
