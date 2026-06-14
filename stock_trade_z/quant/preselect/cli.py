"""CLI for quantitative preselect."""

from __future__ import annotations

import argparse
import sys

from stock_trade_z.lib.logger import get_logger
from stock_trade_z.quant.preselect.pipeline_io import save_candidates, today_iso
from stock_trade_z.quant.preselect.preselect import resolve_preselect_output_dir, run_preselect
from stock_trade_z.quant.preselect.schemas import CandidateRun

logger = get_logger("quant")


def cmd_preselect(args: argparse.Namespace) -> None:
    logger.info("===== 量化初选开始 =====")

    pick_ts, candidates = run_preselect(
        config_path=args.config or None,
        data_dir=args.data or None,
        end_date=args.end_date or None,
        pick_date=args.date or None,
    )

    pick_date_str = pick_ts.strftime("%Y-%m-%d")

    run = CandidateRun(
        run_date=today_iso(),
        pick_date=pick_date_str,
        candidates=candidates,
        meta={
            "config": args.config,
            "data_dir": args.data,
            "total": len(candidates),
        },
    )

    resolved_output_dir = resolve_preselect_output_dir(
        config_path=args.config or None,
        output_dir=args.output or None,
    )

    paths = save_candidates(run, candidates_dir=resolved_output_dir)

    logger.info("===== 初选完成 =====")
    logger.info("选股日期  : %s", pick_date_str)
    logger.info("候选数量  : %d 只", len(candidates))
    for key, path in paths.items():
        logger.info("%-8s → %s", key, path)

    if candidates:
        logger.info("代码     策略   收盘价   砖型增长")
        for c in candidates:
            bg = f"{c.brick_growth:.2f}x" if c.brick_growth is not None else "—"
            logger.info("%s  %s  %.2f  %s", c.code, c.strategy, c.close, bg)
    else:
        logger.info("今日无候选股票")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="量化初选 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("preselect", help="运行量化初选")
    p.add_argument("--config", default=None, help="rules_preselect.yaml 路径")
    p.add_argument("--data", default=None, help="CSV 数据目录")
    p.add_argument("--date", default=None, help="选股基准日期 YYYY-MM-DD")
    p.add_argument("--end-date", dest="end_date", default=None, help="数据截断日期")
    p.add_argument("--output", default=None, help="候选输出目录")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "preselect":
        cmd_preselect(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
