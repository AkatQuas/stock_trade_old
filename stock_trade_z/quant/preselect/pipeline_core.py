"""Data pipeline infrastructure for quantitative preselect."""

from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from typing import Any

import numpy as np
import pandas as pd
from tqdm import tqdm

from stock_trade_z.quant.preselect.selector_engine import (
    AnySelector,
    compute_weekly_ma_bull,
    compute_zx_lines,
)


def _prepare_worker(args: tuple) -> tuple[str, pd.DataFrame | None]:
    code, df, start, end, warmup_bars, n_turnover_days, selector = args

    df = df.copy()
    df.columns = [c.lower() for c in df.columns]

    if "date" not in df.columns:
        return code, None
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    if start is not None:
        dates = df["date"].values
        idx_start = int(np.searchsorted(dates, start.to_datetime64(), side="left"))
        if idx_start >= len(df):
            return code, None
        warmup_start = max(0, idx_start - warmup_bars)
        df = df.iloc[warmup_start:].reset_index(drop=True)

    if end is not None:
        df = df[df["date"] <= end].reset_index(drop=True)

    if df.empty:
        return code, None

    for col in ("open", "close", "volume"):
        if col not in df.columns:
            return code, None
    o, c, v = df["open"], df["close"], df["volume"]
    df["signed_turnover"] = (o + c) / 2 * v
    df["turnover_n"] = df["signed_turnover"].rolling(n_turnover_days, min_periods=1).sum()

    df = df.set_index("date", drop=False)

    if selector is not None and hasattr(selector, "prepare_df"):
        df = selector.prepare_df(df)

    return code, df


def _selector_worker(
    args: tuple[
        str,
        pd.DataFrame,
        AnySelector,
        pd.Timestamp | None,
        pd.Timestamp | None,
        dict[pd.Timestamp, set] | None,
    ],
):
    code, df, selector, start, end, top_turnover_pool_sets = args

    dates = df.index.tolist() if isinstance(df.index, pd.DatetimeIndex) else df["date"].tolist()
    passed_dates: list[pd.Timestamp] = []

    for d in dates:
        if start is not None and d < start:
            continue
        if end is not None and d > end:
            break

        if top_turnover_pool_sets is not None:
            codes_today = top_turnover_pool_sets.get(d)
            if not codes_today or code not in codes_today:
                continue

        if selector.passes_df_on_date(df, d):
            passed_dates.append(d)

    return code, passed_dates


class MarketDataPreparer:
    def __init__(
        self,
        *,
        start_date=None,
        end_date=None,
        warmup_bars: int = 250,
        n_turnover_days: int = 20,
        selector: AnySelector | None = None,
        n_jobs: int | None = None,
    ) -> None:
        self.start_date = start_date
        self.end_date = end_date
        self.warmup_bars = int(warmup_bars)
        self.n_turnover_days = int(n_turnover_days)
        self.selector = selector
        self.n_jobs = n_jobs

    def prepare(self, data: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        tasks = [
            (
                code,
                df,
                self.start_date,
                self.end_date,
                self.warmup_bars,
                self.n_turnover_days,
                self.selector,
            )
            for code, df in data.items()
        ]
        prepared: dict[str, pd.DataFrame] = {}
        with ProcessPoolExecutor(max_workers=self.n_jobs) as ex:
            futures = {ex.submit(_prepare_worker, args): args[0] for args in tasks}
            for fut in tqdm(
                as_completed(futures), total=len(futures), desc="准备数据 (mp)", ncols=80
            ):
                code, df_out = fut.result()
                if df_out is not None:
                    prepared[code] = df_out
        return prepared

    def prepare_base_only(self, data: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        tasks = [
            (code, df, self.start_date, self.end_date, self.warmup_bars, self.n_turnover_days, None)
            for code, df in data.items()
        ]
        prepared: dict[str, pd.DataFrame] = {}
        with ProcessPoolExecutor(max_workers=self.n_jobs) as ex:
            futures = {ex.submit(_prepare_worker, args): args[0] for args in tasks}
            for fut in tqdm(
                as_completed(futures), total=len(futures), desc="基础数据准备 (mp)", ncols=80
            ):
                code, df_out = fut.result()
                if df_out is not None:
                    prepared[code] = df_out
        return prepared

    def apply_selector_features(
        self,
        base_prepared: dict[str, pd.DataFrame],
        selector: Any,
        n_jobs: int | None = None,
    ) -> dict[str, pd.DataFrame]:
        if not hasattr(selector, "prepare_df"):
            return {code: df.copy() for code, df in base_prepared.items()}

        def _apply_one(item):
            code, df = item
            return code, selector.prepare_df(df)

        prepared: dict[str, pd.DataFrame] = {}
        with ThreadPoolExecutor(max_workers=n_jobs or self.n_jobs) as ex:
            futures = {ex.submit(_apply_one, item): item[0] for item in base_prepared.items()}
            for fut in as_completed(futures):
                code, df_out = fut.result()
                if df_out is not None:
                    prepared[code] = df_out
        return prepared

    def apply_zx_wma_features(
        self,
        base_prepared: dict[str, pd.DataFrame],
        selector: Any,
        n_jobs: int | None = None,
    ) -> dict[str, pd.DataFrame]:
        def _apply_one(item):
            code, df = item
            df = df.copy()
            zxdq_ser, zxdkx_ser = compute_zx_lines(
                df,
                selector.zxdkx_m1,
                selector.zxdkx_m2,
                selector.zxdkx_m3,
                selector.zxdkx_m4,
                zxdq_span=selector.zxdq_span,
            )
            df["zxdq"] = zxdq_ser
            df["zxdkx"] = zxdkx_ser
            df["wma_bull"] = compute_weekly_ma_bull(
                df, ma_periods=(selector.wma_short, selector.wma_mid, selector.wma_long)
            ).values
            return code, df

        prepared: dict[str, pd.DataFrame] = {}
        with ThreadPoolExecutor(max_workers=n_jobs or self.n_jobs) as ex:
            futures = {ex.submit(_apply_one, item): item[0] for item in base_prepared.items()}
            for fut in as_completed(futures):
                code, df_out = fut.result()
                if df_out is not None:
                    prepared[code] = df_out
        return prepared

    @staticmethod
    def build_all_dates(prepared: dict[str, pd.DataFrame]) -> list[pd.Timestamp]:
        all_dates: set[pd.Timestamp] = set()
        for df in prepared.values():
            all_dates.update(df.index)
        return sorted(all_dates)


class TopTurnoverPoolBuilder:
    def __init__(self, top_m: int) -> None:
        self.top_m = int(top_m)

    def build(self, prepared: dict[str, pd.DataFrame]) -> dict[pd.Timestamp, list[str]]:
        if self.top_m <= 0:
            return {}

        pool: dict[pd.Timestamp, list[tuple[float, str]]] = defaultdict(list)
        for code, df in prepared.items():
            for dt, val in df["turnover_n"].items():
                pool[dt].append((float(val), code))

        top_codes_by_date: dict[pd.Timestamp, list[str]] = {}
        for dt, lst in pool.items():
            if not lst:
                continue
            lst_sorted = sorted(lst, key=lambda x: x[0], reverse=True)[: self.top_m]
            top_codes_by_date[dt] = [code for _, code in lst_sorted]
        return top_codes_by_date
