"""Build Lark markdown for quant pipeline reports."""

from __future__ import annotations

from typing import Any


def build_quant_report_md(
    candidates: list[dict[str, Any]],
    pick_date: str,
    stocklist: list[dict[str, Any]],
    suggestion: dict[str, Any] | None = None,
    review_provider: str = "vl",
) -> str:
    lines: list[str] = []
    lines.append(f"# 量化初选 + VL 视觉复评 ({pick_date})")
    lines.append("")
    if review_provider:
        lines.append(f"复评模型: {review_provider}")
        lines.append("")

    if not candidates:
        lines.append("本轮量化初选无候选股票。")
    else:
        lines.append(f"## 初选候选 ({len(candidates)} 只)")
        lines.append("")
        for c in candidates:
            code = c.get("code", "")
            strategy = c.get("strategy", "")
            close = c.get("close", "")
            info = next((s for s in stocklist if s.get("symbol") == code), None)
            if info:
                name = info.get("name", "")
                url = info.get("xueqiu_url", "")
                lines.append(f"- {code} {name} [{strategy}] 收盘 {close} — {url}")
            else:
                lines.append(f"- {code} [{strategy}] 收盘 {close}")

    if suggestion is None:
        lines.append("")
        lines.append("## VL 视觉复评推荐")
        lines.append("")
        lines.append("未完成 VL 视觉复评或无评分结果。")
        return "\n".join(lines).strip()

    lines.append("")
    lines.append("## VL 视觉复评推荐")
    lines.append("")
    min_score = suggestion.get("min_score_threshold", 0)
    total = suggestion.get("total_reviewed", 0)
    lines.append(f"评审 {total} 只，推荐门槛 score ≥ {min_score}")
    lines.append("")

    recommendations = suggestion.get("recommendations", [])
    if recommendations:
        lines.append("### 达标推荐")
        lines.append("")
        for r in recommendations:
            code = r.get("code", "")
            info = next((s for s in stocklist if s.get("symbol") == code), None)
            name = info.get("name", "") if info else ""
            url = info.get("xueqiu_url", "") if info else ""
            score = r.get("total_score", "")
            verdict = r.get("verdict", "")
            signal = r.get("signal_type", "")
            comment = r.get("comment", "")
            rank = r.get("rank", "")
            label = f"{code} {name}".strip()
            if url:
                lines.append(
                    f"{rank}. {label} — score {score} [{verdict}] {signal}: {comment} ({url})"
                )
            else:
                lines.append(f"{rank}. {label} — score {score} [{verdict}] {signal}: {comment}")
    else:
        lines.append("暂无达标推荐股票。")

    excluded = suggestion.get("excluded", [])
    if excluded:
        lines.append("")
        lines.append("### 未达标")
        lines.append("")
        lines.append(", ".join(excluded))

    return "\n".join(lines).strip()
