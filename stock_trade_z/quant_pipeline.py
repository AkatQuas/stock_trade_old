"""
quant_pipeline.py
~~~~~~~~~~~~~~~~~
量化选股全流程编排（跳过 K 线抓取，复用 stock-fetch-kline 结果）：

  步骤 1  量化初选（B1 / 砖型图）
  步骤 2  导出候选股 K 线图
  步骤 3  VL 视觉模型图表复评
  步骤 4  打印推荐 + 可选飞书推送
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from stock_trade_z.lib.lark_notify import send_report_as_doc
from stock_trade_z.lib.load_stocklist import load_total_stocklist
from stock_trade_z.lib.logger import get_logger
from stock_trade_z.lib.paths import get_project_root
from stock_trade_z.quant.charts.export_kline_charts import export_charts
from stock_trade_z.quant.preselect.pipeline_io import save_candidates, today_iso
from stock_trade_z.quant.preselect.preselect import resolve_preselect_output_dir, run_preselect
from stock_trade_z.quant.preselect.schemas import CandidateRun
from stock_trade_z.quant.report import build_quant_report_md
from stock_trade_z.quant.review.vision_review import VisionReview

logger = get_logger("quant")


def _print_recommendations(suggestion_file: Path) -> None:
    if not suggestion_file.exists():
        logger.error("找不到评分汇总文件: %s", suggestion_file)
        return

    suggestion: dict = json.loads(suggestion_file.read_text(encoding="utf-8"))
    recommendations: list[dict] = suggestion.get("recommendations", [])
    min_score: float = suggestion.get("min_score_threshold", 0)
    total: int = suggestion.get("total_reviewed", 0)
    pick_date = suggestion.get("date", "")

    logger.info("选股日期: %s  评审总数: %d  推荐门槛: score ≥ %s", pick_date, total, min_score)

    if not recommendations:
        logger.info("暂无达标推荐股票")
        return

    for r in recommendations:
        logger.info(
            "排名 %s  %s  总分 %s  信号 %s  研判 %s  %s",
            r.get("rank", "?"),
            r.get("code", "?"),
            r.get("total_score", "?"),
            r.get("signal_type", ""),
            r.get("verdict", ""),
            r.get("comment", ""),
        )


def _run_preselect_step(
    *,
    data_dir: Path,
    config_path: Path | None,
    pick_date: str | None,
) -> tuple[str, list[dict], Path]:
    pick_ts, candidates = run_preselect(
        config_path=config_path,
        data_dir=data_dir,
        pick_date=pick_date,
    )
    pick_date_str = pick_ts.strftime("%Y-%m-%d")

    run = CandidateRun(
        run_date=today_iso(),
        pick_date=pick_date_str,
        candidates=candidates,
        meta={"data_dir": str(data_dir), "total": len(candidates)},
    )
    output_dir = resolve_preselect_output_dir(config_path=config_path)
    paths = save_candidates(run, candidates_dir=output_dir)
    latest = paths.get("latest", output_dir / "candidates_latest.json")

    candidate_dicts = [c.to_dict() for c in candidates]
    return pick_date_str, candidate_dicts, latest


def main() -> None:
    parser = argparse.ArgumentParser(description="量化初选 + K线图 + VL 视觉复评全流程")
    parser.add_argument("--data-dir", type=Path, default=Path("./data"), help="K 线 CSV 目录")
    parser.add_argument("--config", type=Path, default=None, help="rules_preselect.yaml 路径")
    parser.add_argument(
        "--review-config",
        type=Path,
        default=None,
        help="VL 复评配置路径（默认 config/vision_review.yaml）",
    )
    parser.add_argument("--date", default=None, help="选股基准日期 YYYY-MM-DD")
    parser.add_argument(
        "--start-from", type=int, default=1, metavar="N", help="从第 N 步开始 (1~3)"
    )
    parser.add_argument("--skip-charts", action="store_true", help="跳过 K 线图导出")
    parser.add_argument("--skip-review", action="store_true", help="跳过 VL 视觉复评")
    parser.add_argument("--send-lark", action="store_true", help="发送飞书报告")
    args = parser.parse_args()

    data_dir = args.data_dir
    if not data_dir.exists():
        logger.error("数据目录 %s 不存在", data_dir)
        sys.exit(1)

    vision_review = VisionReview(config_path=args.review_config)

    start = args.start_from
    pick_date_str = args.date or ""
    candidate_dicts: list[dict] = []
    candidates_latest = get_project_root() / "data" / "candidates" / "candidates_latest.json"
    suggestion: dict | None = None

    if start <= 1:
        logger.info("===== 步骤 1/3 量化初选 =====")
        pick_date_str, candidate_dicts, candidates_latest = _run_preselect_step(
            data_dir=data_dir,
            config_path=args.config,
            pick_date=args.date,
        )
    else:
        if candidates_latest.exists():
            data = json.loads(candidates_latest.read_text(encoding="utf-8"))
            pick_date_str = data.get("pick_date", pick_date_str)
            candidate_dicts = data.get("candidates", [])
        else:
            logger.error("跳过初选但找不到 %s", candidates_latest)
            sys.exit(1)

    if start <= 2 and not args.skip_charts:
        if candidate_dicts:
            logger.info("===== 步骤 2/3 导出 K 线图 =====")
            export_charts(raw_dir=data_dir)
        else:
            logger.info("无候选股票，跳过 K 线图导出")

    if start <= 3 and not args.skip_review:
        if candidate_dicts:
            logger.info(
                "===== 步骤 3/3 VL 视觉复评 (provider=%s) =====",
                vision_review.provider,
            )
            suggestion = vision_review.run()
        else:
            logger.info("无候选股票，跳过 VL 视觉复评")

    suggestion_file = vision_review.suggestion_file(pick_date_str)
    if suggestion is None and suggestion_file.exists():
        suggestion = json.loads(suggestion_file.read_text(encoding="utf-8"))

    logger.info("===== 推荐结果 =====")
    if suggestion:
        _print_recommendations(suggestion_file)
    elif candidate_dicts:
        logger.info("无 VL 评分汇总（可能已 --skip-review）")
    else:
        logger.info("本轮无候选股票")

    if args.send_lark:
        stocklist = load_total_stocklist()
        title = f"{pick_date_str} 量化初选+VL推荐"
        markdown = build_quant_report_md(
            candidates=candidate_dicts,
            pick_date=pick_date_str,
            stocklist=stocklist,
            suggestion=suggestion,
            review_provider=vision_review.provider,
        )
        summary = f"📊 量化选股 — {pick_date_str}"
        if send_report_as_doc(title=title, markdown=markdown, summary=summary):
            logger.info("已发送量化报告到 Lark")
        else:
            logger.error("发送 Lark 通知失败")


if __name__ == "__main__":
    main()
