"""Quantitative preselect: B1 and brick chart strategies."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from stock_trade_z.lib.logger import get_logger
from stock_trade_z.lib.paths import get_config_path, get_project_root
from stock_trade_z.quant.preselect.pipeline_core import MarketDataPreparer, TopTurnoverPoolBuilder
from stock_trade_z.quant.preselect.schemas import Candidate
from stock_trade_z.quant.preselect.selector_engine import B1Selector, BrickChartSelector

logger = get_logger("quant")

_DEFAULT_CONFIG = get_config_path("rules_preselect.yaml")


def _resolve_cfg_path(path_like: str | Path, base_dir: Path | None = None) -> Path:
    base = base_dir or get_project_root()
    p = Path(path_like)
    return p if p.is_absolute() else (base / p)


def load_config(config_path: str | Path | None = None) -> dict:
    path = _resolve_cfg_path(config_path) if config_path else _DEFAULT_CONFIG
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg or {}


def resolve_preselect_output_dir(
    *,
    config_path: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> Path:
    if output_dir:
        return _resolve_cfg_path(output_dir)
    cfg = load_config(config_path)
    g = cfg.get("global", {})
    return _resolve_cfg_path(g.get("output_dir", "./data/candidates"))


def load_raw_data(data_dir: str | Path, end_date: str | None = None) -> dict[str, pd.DataFrame]:
    data_path = Path(data_dir)
    if not data_path.is_dir():
        raise FileNotFoundError(f"data_dir 不存在: {data_dir}")

    end_ts = pd.to_datetime(end_date) if end_date else None
    data: dict[str, pd.DataFrame] = {}

    for fname in os.listdir(data_path):
        if not fname.lower().endswith(".csv"):
            continue
        code = fname.rsplit(".", 1)[0]
        fpath = data_path / fname

        df = pd.read_csv(fpath)
        df.columns = [c.lower() for c in df.columns]
        if "date" not in df.columns:
            logger.warning("跳过 %s：没有 date 列", fname)
            continue

        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)

        if end_ts is not None:
            df = df[df["date"] <= end_ts].reset_index(drop=True)

        if not df.empty:
            data[code] = df

    if not data:
        raise ValueError(f"未找到任何 CSV 数据: {data_dir}")

    logger.info("读取股票数量: %d", len(data))
    return data


def _sorted_zx(m1: int, m2: int, m3: int, m4: int) -> tuple[int, int, int, int]:
    a = sorted([int(m1), int(m2), int(m3), int(m4)])
    return a[0], a[1], a[2], a[3]


def _resolve_pick_date(
    prepared: dict[str, pd.DataFrame],
    pick_date: str | None = None,
) -> pd.Timestamp:
    all_dates = sorted(
        {d for df in prepared.values() if isinstance(df.index, pd.DatetimeIndex) for d in df.index}
    )
    if not all_dates:
        raise ValueError("prepared 数据中没有可用日期。")
    if pick_date is None:
        return all_dates[-1]

    target = pd.to_datetime(pick_date)
    arr = np.array(all_dates, dtype="datetime64[ns]")
    idx = int(np.searchsorted(arr, target.to_datetime64(), side="right")) - 1
    if idx < 0:
        raise ValueError(f"pick_date={pick_date} 早于最早可用日期={all_dates[0].date()}")
    return all_dates[idx]


def _calc_warmup(cfg: dict, buffer: int) -> int:
    warmup = 120

    cfg_b1 = cfg.get("b1", {})
    if cfg_b1.get("enabled", True):
        warmup = max(warmup, int(cfg_b1.get("zx_m4", 371)) + buffer)

    cfg_brick = cfg.get("brick", {})
    if cfg_brick.get("enabled", True):
        warmup = max(
            warmup,
            int(cfg_brick.get("wma_long", 120)) * 5 + buffer,
            int(cfg_brick.get("zxdkx_m4", 114)) + buffer,
        )

    return warmup


def _build_pool_codes(
    prepared: dict[str, pd.DataFrame],
    pick_ts: pd.Timestamp,
    cfg: dict,
) -> list[str]:
    g = cfg.get("global", {})
    liquidity_cfg = g.get("liquidity_pool", {})
    if liquidity_cfg.get("enabled", True) is False:
        pool_codes = list(prepared.keys())
        logger.info("流动性池已关闭，扫描全量: %d 只", len(pool_codes))
        return pool_codes

    top_m = int(g.get("top_m", 20))
    pool_codes = TopTurnoverPoolBuilder(top_m=top_m).build(prepared).get(pick_ts, [])
    logger.info("流动性池: %d 只 (top_m=%d)", len(pool_codes), top_m)
    return pool_codes


def run_b1(
    prepared: dict[str, pd.DataFrame],
    pick_date: pd.Timestamp,
    pool_codes: list[str],
    cfg_b1: dict,
) -> list[Candidate]:
    zx_m1, zx_m2, zx_m3, zx_m4 = _sorted_zx(
        cfg_b1["zx_m1"], cfg_b1["zx_m2"], cfg_b1["zx_m3"], cfg_b1["zx_m4"]
    )
    selector = B1Selector(
        j_threshold=float(cfg_b1["j_threshold"]),
        j_q_threshold=float(cfg_b1["j_q_threshold"]),
        zx_m1=zx_m1,
        zx_m2=zx_m2,
        zx_m3=zx_m3,
        zx_m4=zx_m4,
    )

    date_str = pick_date.strftime("%Y-%m-%d")
    candidates: list[Candidate] = []

    for code in pool_codes:
        df = prepared.get(code)
        if df is None or pick_date not in df.index:
            continue
        try:
            pf = selector.prepare_df(df)
            if selector.vec_picks_from_prepared(pf, start=pick_date, end=pick_date):
                row = pf.loc[pick_date]
                candidates.append(
                    Candidate(
                        code=code,
                        date=date_str,
                        strategy="b1",
                        close=float(row["close"]),
                        turnover_n=float(row["turnover_n"]),
                    )
                )
        except Exception as exc:
            logger.debug("B1 skip %s: %s", code, exc)

    logger.info("B1 选出: %d 只", len(candidates))
    return candidates


def run_brick(
    prepared: dict[str, pd.DataFrame],
    pick_date: pd.Timestamp,
    pool_codes: list[str],
    cfg_brick: dict,
) -> list[Candidate]:
    selector = BrickChartSelector(
        daily_return_threshold=float(cfg_brick.get("daily_return_threshold", 0.05)),
        brick_growth_ratio=float(cfg_brick.get("brick_growth_ratio", 1.0)),
        min_prior_green_bars=int(cfg_brick.get("min_prior_green_bars", 2)),
        zxdq_ratio=cfg_brick.get("zxdq_ratio"),
        zxdq_span=int(cfg_brick.get("zxdq_span", 10)),
        require_zxdq_gt_zxdkx=bool(cfg_brick.get("require_zxdq_gt_zxdkx", True)),
        zxdkx_m1=int(cfg_brick.get("zxdkx_m1", 14)),
        zxdkx_m2=int(cfg_brick.get("zxdkx_m2", 28)),
        zxdkx_m3=int(cfg_brick.get("zxdkx_m3", 57)),
        zxdkx_m4=int(cfg_brick.get("zxdkx_m4", 114)),
        require_weekly_ma_bull=bool(cfg_brick.get("require_weekly_ma_bull", True)),
        wma_short=int(cfg_brick.get("wma_short", 20)),
        wma_mid=int(cfg_brick.get("wma_mid", 60)),
        wma_long=int(cfg_brick.get("wma_long", 120)),
        n=int(cfg_brick.get("n", 4)),
        m1=int(cfg_brick.get("m1", 4)),
        m2=int(cfg_brick.get("m2", 6)),
        m3=int(cfg_brick.get("m3", 6)),
        t=float(cfg_brick.get("t", 4.0)),
        shift1=float(cfg_brick.get("shift1", 90.0)),
        shift2=float(cfg_brick.get("shift2", 100.0)),
        sma_w1=int(cfg_brick.get("sma_w1", 1)),
        sma_w2=int(cfg_brick.get("sma_w2", 1)),
        sma_w3=int(cfg_brick.get("sma_w3", 1)),
    )

    date_str = pick_date.strftime("%Y-%m-%d")
    candidates: list[Candidate] = []

    for code in pool_codes:
        df = prepared.get(code)
        if df is None or pick_date not in df.index:
            continue
        try:
            pf = selector.prepare_df(df)
            if selector.vec_picks_from_prepared(pf, start=pick_date, end=pick_date):
                row = pf.loc[pick_date]
                if "brick_growth" in pf.columns:
                    bg = float(row["brick_growth"])
                else:
                    bg = selector.brick_growth_on_date(pf, pick_date)
                candidates.append(
                    Candidate(
                        code=code,
                        date=date_str,
                        strategy="brick",
                        close=float(row["close"]),
                        turnover_n=float(row["turnover_n"]),
                        brick_growth=bg if np.isfinite(bg) else None,
                    )
                )
        except Exception as exc:
            logger.debug("Brick skip %s: %s", code, exc)

    candidates.sort(key=lambda c: c.brick_growth or -999, reverse=True)
    logger.info("Brick 选出: %d 只", len(candidates))
    return candidates


def run_preselect(
    *,
    config_path: str | Path | None = None,
    data_dir: str | Path | None = None,
    end_date: str | None = None,
    pick_date: str | None = None,
) -> tuple[pd.Timestamp, list[Candidate]]:
    cfg = load_config(config_path)
    g = cfg.get("global", {})

    resolved_data_dir = _resolve_cfg_path(data_dir or g.get("data_dir", "./data"))
    n_turnover_days = int(g.get("n_turnover_days", 43))
    min_bars_buffer = int(g.get("min_bars_buffer", 10))

    raw_data = load_raw_data(resolved_data_dir, end_date=end_date)
    warmup = _calc_warmup(cfg, min_bars_buffer)

    preparer = MarketDataPreparer(
        end_date=pd.to_datetime(end_date) if end_date else None,
        warmup_bars=warmup,
        n_turnover_days=n_turnover_days,
        selector=None,
    )
    prepared = preparer.prepare(raw_data)

    pick_ts = _resolve_pick_date(prepared, pick_date)
    logger.info("选股日期: %s", pick_ts.date())

    pool_codes = _build_pool_codes(prepared, pick_ts, cfg)
    if not pool_codes:
        logger.warning("扫描池为空，pick_date=%s", pick_ts.date())
        return pick_ts, []

    all_candidates: list[Candidate] = []

    if cfg.get("b1", {}).get("enabled", True):
        all_candidates.extend(run_b1(prepared, pick_ts, pool_codes, cfg["b1"]))

    if cfg.get("brick", {}).get("enabled", True):
        all_candidates.extend(run_brick(prepared, pick_ts, pool_codes, cfg["brick"]))

    seen: set[str] = set()
    deduped: list[Candidate] = []
    for c in all_candidates:
        if c.code in seen:
            continue
        seen.add(c.code)
        deduped.append(c)

    logger.info("初选完成，候选股票: %d 只", len(deduped))
    return pick_ts, deduped
