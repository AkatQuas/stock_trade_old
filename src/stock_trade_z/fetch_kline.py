from __future__ import annotations

import argparse
import datetime as dt
import sys
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from stock_trade_z.lib.fetch_data import fetch_one_data
from stock_trade_z.lib.load_stocklist import StockCodeDict, load_stock_from_file
from stock_trade_z.lib.logger import get_logger
from stock_trade_z.lib.utils import ensure_folder, random_sleep_50_to_150ms, sleep_progress

warnings.filterwarnings("ignore")

logger = get_logger("fetch")


def save_one_data(
    stock: StockCodeDict,
    start: str,
    end: str,
    out_dir: Path,
) -> pd.DataFrame | None:
    name = f"{stock['symbol']}"
    random_sleep_50_to_150ms()
    new_df = fetch_one_data(stock["symbol"], start, end)
    if new_df is None:
        logger.error("%s 抓取失败，已跳过！", name)
        return None

    csv_path = out_dir / f"{name}.csv"
    new_df.to_csv(csv_path, index=False)  # 直接覆盖保存
    return new_df


# --------------------------- 主入口 --------------------------- #
def main():
    parser = argparse.ArgumentParser(
        description="从 stocklist.csv 读取股票池并用 Tushare 抓取日线K线（固定qfq，全量覆盖）"
    )
    # 抓取范围
    parser.add_argument("--start", default="20250101", help="起始日期 YYYYMMDD 或 'today'")
    parser.add_argument("--end", default="today", help="结束日期 YYYYMMDD 或 'today'")
    # 股票清单与板块过滤
    parser.add_argument(
        "--stocklist",
        type=Path,
        help="股票清单CSV路径（需含 ts_code 或 symbol）",
    )
    parser.add_argument(
        "--exclude-boards",
        nargs="*",
        default=["star", "bj"],
        choices=["gem", "star", "bj"],
        help="排除板块，可多选：gem(创业板300/301) star(科创板688) bj(北交所.BJ/4/8)",
    )
    # 其它
    parser.add_argument("--out", default=Path, help="输出目录")
    parser.add_argument("--workers", type=int, default=6, help="并发线程数")
    parser.add_argument(
        "--chunk",
        type=int,
        default=48,
        help="单次请求的 chunk 大小，避免命中频控限制，默认为 48 个一组",
    )
    parser.add_argument(
        "--chunk_sleep",
        type=int,
        default=65,
        help="每个 chunk 请求之间的睡眠时长，默认为 65 秒，设置为 0 则不睡眠",
    )
    args = parser.parse_args()

    # ---------- 从 stocklist.csv 读取股票池 ---------- #
    exclude_boards = set(args.exclude_boards or [])
    stock_list = load_stock_from_file(args.stocklist, exclude_boards)

    if len(stock_list) == 0:
        logger.error("stocklist 为空或被过滤后无代码，请检查。")
        sys.exit(1)

    # ---------- Tushare Token ---------- #

    # ---------- 日期解析 ---------- #
    start = dt.date.today().strftime("%Y%m%d") if str(args.start).lower() == "today" else args.start
    end = dt.date.today().strftime("%Y%m%d") if str(args.end).lower() == "today" else args.end

    out_dir = ensure_folder(args.out)

    logger.info(
        "开始抓取 %d 支股票 | 数据源:Tushare(日线,qfq) | 日期:%s → %s | 排除:%s",
        len(stock_list),
        start,
        end,
        ",".join(sorted(exclude_boards)) or "无",
    )

    chunk_size = args.chunk
    chunk_list = [stock_list[i : i + chunk_size] for i in range(0, len(stock_list), chunk_size)]
    logger.info("== 一共有 %s 个 chunk 任务 ==", len(chunk_list))
    # ---------- 多线程抓取（全量覆盖） ---------- #
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for idx, chunk in enumerate(chunk_list):
            task_idx = idx + 1
            logger.info(
                "任务 chunk %s running, 剩余 %s 个 chunk",
                task_idx,
                len(chunk_list) - task_idx,
            )
            futures = [
                executor.submit(
                    save_one_data,
                    stock,
                    start,
                    end,
                    out_dir,
                )
                for stock in chunk
            ]
            for _ in tqdm(
                as_completed(futures),
                total=len(futures),
                desc=f"chunk {task_idx} 的下载进度",
            ):
                pass
            if args.chunk_sleep > 0 and task_idx < len(chunk_list):
                sleep_progress(args.chunk_sleep)

    logger.info("全部任务完成，数据已保存至 %s", out_dir.resolve())


if __name__ == "__main__":
    main()
