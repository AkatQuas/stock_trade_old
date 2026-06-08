"""LLM rank + explain + second-opinion for selector shortlists."""

from __future__ import annotations

import json
import re
from typing import Any

import pandas as pd

from .llm import DEFAULT_MODEL, api_key_configured, complete
from .logger import get_logger

logger = get_logger("select")

ANALYZE_MAX_TOKENS = 4096


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("LLM 返回非 JSON")
    return json.loads(match.group(0))


def analyze_picks(
    records: list[dict[str, Any]],
    trade_date: pd.Timestamp,
    *,
    track: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = ANALYZE_MAX_TOKENS,
) -> dict[str, Any] | None:
    """Rank and annotate picks; returns None if LLM unavailable or fails."""
    if not api_key_configured():
        logger.warning("DEEPSEEK_API_KEY 未设置，跳过 LLM 分析")
        return None
    if not records:
        return {"trade_date": str(trade_date.date()), "ranked": [], "dropped": []}

    payload = {"trade_date": str(trade_date.date()), "track": track, "picks": records}
    picks_json = json.dumps(payload, ensure_ascii=False, indent=2)

    prompt = f"""你是 A 股短线选股研究员，为人工复盘提供第二意见（非投资建议）。

以下是由规则选股器产生的候选列表（track={track}），请：
1. 按短期质量重新排序（rank 从 1 开始）
2. 为每只给出 verdict: keep（推荐）| flag（谨慎）| veto（建议剔除）
3. 用中文简述 reason（1-2 句）和 risks（列表）

仅根据提供的结构化数据判断，不要编造新闻或财报。
输出必须是纯 JSON（不要 markdown 代码块），格式：
{{
  "trade_date": "{trade_date.date()}",
  "ranked": [
    {{"symbol": "600000", "rank": 1, "score": 0.0, "verdict": "keep", "reason": "...", "risks": ["..."]}}
  ],
  "dropped": [
    {{"symbol": "000001", "verdict": "veto", "reason": "..."}}
  ]
}}

候选数据：
{picks_json}"""

    try:
        raw = complete(prompt, model=model, max_tokens=max_tokens)
        return _extract_json(raw)
    except Exception as e:
        logger.error("LLM 分析失败: %s", e)
        return None


def format_llm_lark_section(analysis: dict[str, Any] | None) -> str | None:
    if not analysis:
        return None

    lines: list[str] = ["**🤖 LLM 复盘**"]
    ranked = analysis.get("ranked") or []
    if not ranked:
        lines.append("无排序结果")
        return "\n".join(lines)

    for item in ranked[:15]:
        sym = item.get("symbol", "")
        verdict = item.get("verdict", "keep")
        icon = {"keep": "✅", "flag": "⚠️", "veto": "❌"}.get(verdict, "•")
        reason = item.get("reason", "")
        risks = item.get("risks") or []
        risk_txt = f" | 风险: {', '.join(risks)}" if risks else ""
        lines.append(f"{icon} {sym} [{verdict}] {reason}{risk_txt}")

    dropped = analysis.get("dropped") or []
    if dropped:
        lines.append("\n**剔除**")
        for item in dropped[:5]:
            lines.append(f"❌ {item.get('symbol')} — {item.get('reason', '')}")

    return "\n".join(lines)
