"""Batch export candidate K-line charts as JPEG images."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from stock_trade_z.lib.logger import get_logger
from stock_trade_z.lib.paths import get_project_root
from stock_trade_z.quant.charts.components.charts import make_daily_chart

logger = get_logger("quant")

DEFAULT_BARS = 120
DEFAULT_DAY_WIDTH = 1400
DEFAULT_DAY_HEIGHT = 700


def _load_candidates(candidates_path: Path) -> tuple[list[str], str]:
    if not candidates_path.exists():
        raise FileNotFoundError(f"候选文件不存在: {candidates_path}")
    data = json.loads(candidates_path.read_text(encoding="utf-8"))
    codes = [c["code"] for c in data.get("candidates", [])]
    pick_date = data.get("pick_date", "")
    logger.info(
        "候选股票数量: %d  pick_date: %s  来源: %s",
        len(codes),
        pick_date or "(未设置)",
        candidates_path.name,
    )
    return codes, pick_date


def _load_raw(code: str, raw_dir: Path) -> pd.DataFrame:
    csv = raw_dir / f"{code}.csv"
    if not csv.exists():
        return pd.DataFrame()
    df = pd.read_csv(csv)
    df.columns = [c.lower() for c in df.columns]
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def _export_fig(fig, out_path: Path, width: int, height: int) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_image(str(out_path), format="jpg", width=width, height=height, scale=2)


def export_charts(
    *,
    candidates_path: Path | None = None,
    raw_dir: Path | None = None,
    out_dir: Path | None = None,
    bars: int = DEFAULT_BARS,
    day_width: int = DEFAULT_DAY_WIDTH,
    day_height: int = DEFAULT_DAY_HEIGHT,
) -> tuple[int, int, Path | None]:
    """Export daily charts for all candidates. Returns (ok_count, skip_count, out_root)."""
    root = get_project_root()
    candidates_path = candidates_path or (root / "data" / "candidates" / "candidates_latest.json")
    raw_dir = raw_dir or (root / "data")
    out_base = out_dir or (root / "data" / "kline")

    codes, pick_date = _load_candidates(candidates_path)
    if not pick_date:
        raise ValueError("candidates.json 中未设置 pick_date")

    if not codes:
        logger.info("无候选股票，跳过 K 线图导出")
        return 0, 0, None

    out_root = out_base / pick_date
    ok_count = 0
    skip_count = 0

    for code in codes:
        df_raw = _load_raw(code, raw_dir)
        if df_raw.empty:
            logger.warning("跳过 %s: 无日线数据", code)
            skip_count += 1
            continue

        day_path = out_root / f"{code}_day.jpg"
        try:
            fig_day = make_daily_chart(df_raw, code, bars=bars, height=day_height)
            _export_fig(fig_day, day_path, day_width, day_height)
            logger.info("导出 %s → %s", code, day_path.name)
            ok_count += 1
        except Exception as e:
            logger.error("%s 日线导出失败: %s", code, e)
            skip_count += 1

    logger.info("导出完成: 成功 %d 只，跳过 %d 只，目录 %s", ok_count, skip_count, out_root)
    return ok_count, skip_count, out_root


def main() -> None:
    export_charts()


if __name__ == "__main__":
    main()
