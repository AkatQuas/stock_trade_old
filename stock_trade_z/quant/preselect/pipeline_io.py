"""Atomic read/write for candidates JSON artifacts."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from stock_trade_z.lib.logger import get_logger
from stock_trade_z.lib.paths import get_project_root
from stock_trade_z.quant.preselect.schemas import CandidateRun

logger = get_logger("quant")

_DEFAULT_CANDIDATES_DIR = get_project_root() / "data" / "candidates"


def _resolve_path(path_like: str | Path) -> Path:
    p = Path(path_like)
    return p if p.is_absolute() else (get_project_root() / p)


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _atomic_write(path: Path, content: str) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)
    logger.debug("写入完成: %s", path)


def save_candidates(
    run: CandidateRun,
    *,
    candidates_dir: str | Path | None = None,
    write_dated: bool = True,
    write_latest: bool = True,
) -> dict[str, Path]:
    out_dir = _resolve_path(candidates_dir) if candidates_dir else _DEFAULT_CANDIDATES_DIR
    _ensure_dir(out_dir)

    payload = json.dumps(run.to_dict(), ensure_ascii=False, indent=2)
    written: dict[str, Path] = {}

    if write_dated:
        dated_path = out_dir / f"candidates_{run.pick_date}.json"
        _atomic_write(dated_path, payload)
        written["dated"] = dated_path
        logger.info("存档文件: %s", dated_path)

    if write_latest:
        latest_path = out_dir / "candidates_latest.json"
        _atomic_write(latest_path, payload)
        written["latest"] = latest_path
        logger.info("契约文件: %s", latest_path)

    return written


def load_latest(candidates_dir: str | Path | None = None) -> CandidateRun:
    out_dir = _resolve_path(candidates_dir) if candidates_dir else _DEFAULT_CANDIDATES_DIR
    latest_path = out_dir / "candidates_latest.json"
    if not latest_path.exists():
        raise FileNotFoundError(f"契约文件不存在: {latest_path}")
    data = json.loads(latest_path.read_text(encoding="utf-8"))
    return CandidateRun.from_dict(data)


def load_by_date(pick_date: str, candidates_dir: str | Path | None = None) -> CandidateRun:
    out_dir = _resolve_path(candidates_dir) if candidates_dir else _DEFAULT_CANDIDATES_DIR
    path = out_dir / f"candidates_{pick_date}.json"
    if not path.exists():
        raise FileNotFoundError(f"存档文件不存在: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return CandidateRun.from_dict(data)


def today_iso() -> str:
    return date.today().isoformat()
