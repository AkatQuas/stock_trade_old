from datetime import datetime

import pandas as pd


def validate(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    df = df.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
    if df["date"].isna().any():
        raise ValueError("存在缺失日期！")
    if (df["date"] > pd.Timestamp.today()).any():
        raise ValueError("数据包含未来日期，可能抓取错误！")
    return df


def get_today_date():
    return datetime.now().strftime("%Y%m%d")


def get_today_name():
    t = pd.Timestamp.now()
    current_date = t.date()
    current_weekday = t.day_name()
    return f"【今天】{current_date}({current_weekday})"
