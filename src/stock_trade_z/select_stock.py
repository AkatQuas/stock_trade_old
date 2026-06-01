from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from stock_trade_z.lib.data_utils import load_data_folder
from stock_trade_z.lib.load_selector import load_selectors
from stock_trade_z.lib.load_stocklist import load_total_stocklist
from stock_trade_z.lib.logger import get_logger
from stock_trade_z.lib.send_lark_message import build_interactive_card, send_message
from stock_trade_z.lib.time import get_today_name

logger = get_logger("select")


def build_lark_card(trade_date, results: list[dict]) -> dict:
    """Build an interactive card for Lark with selection results."""
    title = f"📈 选股结果 - {trade_date.date()} {trade_date.day_name()}"

    fields = []
    if not results:
        fields.append({"is_short": False, "content": "❌ 本轮无选股结果"})
        return build_interactive_card(title=title, fields=fields, template="carmine")

    for r in results:
        stock_names = "\n".join([f"{s['name']} - {s['url']}" for s in r["stocks"]])
        fields.append(
            {
                "is_short": False,
                "content": f"**{r['selector']}** ({r['count']}只)\n{stock_names}",
            }
        )
    return build_interactive_card(title=title, fields=fields)


def main():
    p = argparse.ArgumentParser(description="Run selectors defined in selector.config.json")
    p.add_argument("--data-dir", type=Path, required=True, help="行情数据目录， CSV K线数据")
    p.add_argument("--date", help="交易日 YYYY-MM-DD ，默认=数据最新日期")
    p.add_argument("--send-lark", action="store_true", help="发送Lark通知")
    args = p.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        logger.error("数据目录 %s 不存在", data_dir)
        sys.exit(1)

    try:
        data, trade_date = load_data_folder(data_dir, date=args.date)
    except Exception as e:
        logger.error("加载行情失败: %s", e)
        sys.exit(1)

    selector_dict = load_selectors()

    stocklist = load_total_stocklist()

    logger.info(
        "🤖 开始本轮选股 🚀 🚀, 交易日: %s %s 。 \n\n",
        trade_date.date(),
        trade_date.day_name(),
    )

    all_results = []
    for alias, selector in selector_dict.items():
        picks = selector.select(trade_date, data)

        if len(picks) > 0:
            logger.info("============ 🎉 🎉 [%s] 选股结果 (%d) ==========", alias, len(picks))
            filtered_list = [s for s in stocklist if s["symbol"] in picks]
            single_str_list = [
                f"{s['symbol']}, {s['name'].ljust(5)}({s['xueqiu_url']})" for s in filtered_list
            ]
            big_string = "\n".join(single_str_list)
            logger.info("\n\n%s\n\n", big_string)

            all_results.append(
                {
                    "selector": alias,
                    "count": len(picks),
                    "stocks": [
                        {
                            "symbol": s["symbol"],
                            "name": s["name"],
                            "url": s["xueqiu_url"],
                        }
                        for s in filtered_list
                    ],
                }
            )
        else:
            logger.info("============ ❌ ❌ [%s] 无结果 =======\n\n", alias)

    logger.info("🤖 选股结束，下次再来。 %s 🏖️️ 🏖️\n", get_today_name())

    if args.send_lark:
        card = build_lark_card(trade_date, all_results)
        receive_id = os.getenv("ME_UNION_ID")
        if receive_id:
            success = send_message(receive_id, card, msg_type="interactive")
            if success:
                logger.info("✅ 已发送选股结果到Lark")
            else:
                logger.error("❌ 发送Lark通知失败")
        else:
            logger.warning("ME_UNION_ID 未配置，跳过Lark通知")


if __name__ == "__main__":
    main()
