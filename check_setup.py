"""
验证所有配置是否就绪，完成后发送一条测试 Lark 消息。
本地运行：uv run python check_setup.py
GitHub Actions：Actions → ✅ Check Setup → Run workflow
"""

import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import tushare as ts
from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

from stock_trade_z.lib.send_lark_message import (  # noqa: E402
    build_interactive_card,
    lark_configured,
    send_message,
)
from stock_trade_z.lib.ts_pro_api import get_pro_api  # noqa: E402

OK = "✅"
FAIL = "❌"
errors: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> bool:
    status = OK if ok else FAIL
    line = f"  {status}  {label}"
    if detail:
        line += f"  ({detail})"
    print(line)
    if not ok:
        errors.append(label)
    return ok


def section(title: str) -> None:
    print(f"\n── {title} {'─' * (50 - len(title))}")


section("环境变量 / GitHub Secrets")
required = {
    "TUSHARE_TOKEN": os.getenv("TUSHARE_TOKEN"),
    "LARK_APP_ID": os.getenv("LARK_APP_ID"),
    "LARK_SECRET": os.getenv("LARK_SECRET"),
    "ME_UNION_ID": os.getenv("ME_UNION_ID"),
}
for name, value in required.items():
    check(name, bool(value), "已设置" if value else "未找到")

section("本地 .env")
env_path = ROOT / ".env"
check(".env 存在", env_path.exists(), str(env_path) if env_path.exists() else "运行 setup.py 生成")

section("Tushare API")
if os.getenv("TUSHARE_TOKEN"):
    try:
        ts_pro = get_pro_api()
        df: pd.DataFrame | None = ts.pro_bar(
            ts_code="000066.SZ",
            adj="qfq",
            start_date="20240701",
            end_date="20260601",
            freq="D",
            api=ts_pro,
            # factors=["tor"]
        )
        check("Tushare API 连接成功", df is not None and len(df) > 0)
    except Exception as e:
        check("Tushare API 连接", False, str(e))
else:
    check("Tushare API 连接（跳过，TUSHARE_TOKEN 未设置）", False)

section("Lark")
if not lark_configured():
    check("Lark 配置完整", False, "需设置 LARK_APP_ID、LARK_SECRET、ME_UNION_ID")
else:
    check("Lark 配置完整", True)
    if not errors:
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            card = build_interactive_card(
                title="✅ Stock Trade Z — 配置验证成功",
                fields=[
                    {
                        "is_short": False,
                        "content": (
                            f"环境已就绪，选股与风控结果可推送到 Lark。\n\n验证时间：{now}"
                        ),
                    },
                    {
                        "is_short": True,
                        "content": "**Tushare**\n已配置",
                    },
                    {
                        "is_short": True,
                        "content": "**飞书机器人**\n已配置",
                    },
                ],
                template="green",
            )
            ok_send = send_message(
                receive_id=os.getenv("ME_UNION_ID"),
                content=card,
                msg_type="interactive",
            )
            check("测试 Lark 消息已发送", ok_send)
        except Exception as e:
            check("发送测试 Lark 消息", False, str(e))
    else:
        print("  ⚠️  存在配置错误，跳过发送测试 Lark 消息")

print("\n" + "═" * 54)
if not errors:
    print("  🎉  所有检查通过！查收 Lark 测试消息后即可运行每日工作流。")
else:
    print(f"  ❌  {len(errors)} 项需要修复：")
    for e in errors:
        print(f"       · {e}")
    print("\n  运行 uv run python setup.py 完成配置后重新检查。")
print("═" * 54)

sys.exit(0 if not errors else 1)
