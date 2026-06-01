## 免责声明

- **股市有风险，入市需谨慎。**
- 本仓库仅供学习与技术研究之用，**不构成任何投资建议**。
- 数据来源与接口可能随平台策略调整而变化，请合法合规使用。
- 致谢 [**@Zettaranc**](https://b23.tv/JxIOaNE) 在 Bilibili 的无私分享
- 致谢 [**@JeffreyZZ331**](https://b23.tv/Ysrdfas) 的开源项目 [StockTradebyZ](https://github.com/SebastienZh/StockTradebyZ)。

---

# Z哥战法的 Python 实现（更新版）

> **更新时间：2025-12-26** –
>
> 新增 **BigBullishVolumeSelector（暴力K战法）**：用于捕捉放量启动、贴近短线均值的强势阳线；

##

## 目录

- [快速上手](#快速上手)
  - [环境与依赖](#环境与依赖)
  - [准备 Tushare Token](#准备-tushare-token)
- [核心功能](#核心功能)
  - [1. 获取股票列表](#1-获取股票列表)
  - [2. 下载历史 K 线（qfq，日线）](#2-下载历史-k-线qfq日线)
  - [3. 运行选股](#3-运行选股)
  - [4. 检查单只股票](#4-检查单只股票)
  - [5. 添加股票到优选列表](#5-添加股票到优选列表)
- [内置策略（Selector）](#内置策略selector)
  - [1. BBIKDJSelector（少妇战法）](#1-bbikdjselector少妇战法)
  - [2. SuperB1Selector（SuperB1战法）](#2-superb1selectorsuperb1战法)
  - [3. BBIShortLongSelector（补票战法）](#3-bbishortlongselector补票战法)
  - [4. PeakKDJSelector（填坑战法）](#4-peakkdjselector填坑战法)
  - [5. MA60CrossVolumeWaveSelector（上穿60放量战法）](#5-ma60crossvolumewaveselector上穿60放量战法)
  - [6. BigBullishVolumeSelector（暴力K战法）](#6-bigbullishvolumeselector暴力k战法)
- [项目结构](#项目结构)
- [常见问题](#常见问题)

---

## 快速上手

### 环境与依赖

本项目为 **uv 标准布局**（`src/stock_trade_z` 可安装包 + `pyproject.toml` + `uv.lock`）。

```bash
cd /path/to/stock_trade_z
uv sync          # 创建 .venv 并安装依赖 + 可编辑安装本包
uv sync --group dev   # 含 ruff（lint + format）
```

**代码检查与格式化（[Ruff](https://docs.astral.sh/ruff/)）：**

```bash
uv run ruff check .              # 静态检查
uv run ruff check --fix .        # 自动修复可修复项
uv run ruff format .             # 格式化
uv run ruff format --check .     # CI 用：仅检查格式是否一致
```

VS Code/Cursor：安装 [Ruff 扩展](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff)，本项目 `.vscode/settings.json` 已配置保存时格式化与 import 整理。

**Git pre-commit（提交前自动检查）：**

```bash
uv sync --group dev
uv run pre-commit install          # 安装 hooks 到 .git/hooks（每台机器执行一次）
uv run pre-commit run --all-files  # 手动全量跑一遍
```

每次 `git commit` 会自动执行：尾随空格/EOF、YAML 检查、Ruff lint（含 `--fix`）与 Ruff format。配置见 [`.pre-commit-config.yaml`](./.pre-commit-config.yaml)。

**CLI 入口（`uv run` 后可直接调用）：**

| 命令 | 说明 |
|------|------|
| `stock-fetch-list` | 拉取全市场股票列表 |
| `stock-fetch-kline` | 下载日线 K 线 CSV |
| `stock-select` | 批量选股 |
| `stock-detect-risk` | 批量风险检测 |
| `stock-check` | 单只股票战法检查 |

> 关键依赖：`pandas`, `tqdm`, `tushare`, `baostock`, `numpy`, `scipy`。

### 准备 Tushare Token

在 [TuShare](https://tushare.pro/) 注册账号，并从 [这里获取 token](https://tushare.pro/user/token)。

1. 长期有效的方式，请更新 `.env.example` 里面的变量值，并重命名为 `.env`。

或者，

2. 在当前 CLI session 下临时使用，请设置变量：

```bash
# Windows (PowerShell)
setx TUSHARE_TOKEN "你的token"

# macOS / Linux (bash)
export TUSHARE_TOKEN=你的token
```

## 核心功能

### 1. 获取股票列表

从 TuShare 获取所有 A 股股票列表，保存到 CSV 文件。建议定期更新，确保数据准确。

```bash
python src/stock_trade_z/fetch_stocklist.py
```

### 2. 下载历史 K 线（qfq，日线）

- **数据源固定**：Tushare 日线，**前复权 qfq**。
- **保存策略**：每只股票**全量覆盖写入** `./data/XXXXXX.csv`。
- **并发抓取**：默认 6 线程；支持封禁冷却（命中「访问频繁/429/403…」将睡眠约 600s 并重试，最多 3 次）。
- **频控处理**：低积分的 token 可能每分钟可调用的接口次数有限，提前对请求做了睡眠处理
- **stocklist.good.csv**：经过初步筛选的股票文件。如需全量的数据，请查看 [stocklist.total.csv](./src/stock_trade_z/stocklist.total.csv) 。

```bash
python src/stock_trade_z/fetch_kline.py \
  --start 20240101 \
  --end today \
  --stocklist ./stocklist.good.csv \
  --exclude-boards gem star bj \
  --out ./data \
  --workers 6 \
  --chunk 48 \
  --chunk_sleep 65
```

**参数说明**

| 参数               | 默认值                  | 说明                                                                                               |
| ------------------ | ----------------------- | -------------------------------------------------------------------------------------------------- |
| `--start`          | `20250101`              | 起始日期，格式 `YYYYMMDD` 或 `today`                                                               |
| `--end`            | `today`                 | 结束日期，格式同上                                                                                 |
| `--stocklist`      | `./stocklist.good.csv`  | 股票清单 CSV 路径（含 `ts_code` 或 `symbol`）                                                      |
| `--exclude-boards` | `["gem", "star", "bj"]` | 排除板块，枚举：`gem`(创业板 300/301) / `star`(科创板 688) / `bj`(北交所 .BJ / 4/8 开头)。可多选。 |
| `--out`            | `./data`                | 输出目录（自动创建）                                                                               |
| `--workers`        | `6`                     | 并发线程数                                                                                         |
| `--chunk`          | `48`                    | 单次请求的任务数，多 chunk 有助于逃过请求频控                                                      |
| `--chunk_sleep`    | `65`                    | 每次请求之间的睡眠时间，用来逃过请求频控                                                           |

**输出 CSV 列**：`date, open, close, high, low, volume`（按日期升序）。

**抓取与重试**：每支股票最多 3 次尝试；疑似限流/封禁触发 **600s 冷却**；其它异常采用递进式短等候重试（15s×尝试次数）。

### 3. 运行选股

批量对股票池执行选股策略，输出符合条件的股票。

```bash
uv run stock-select --data-dir ./data --date 2025-09-10
```

> `--date` 可省略，默认取数据中的最后交易日。

**参数说明**

| 参数         | 默认值         | 说明        |
| ------------ | -------------- | ----------- |
| `--data-dir` | 必填           | K线行情目录 |
| `--date`     | 数据最后交易日 | 选股交易日  |

### 4. 检查单只股票

对指定股票代码进行检查，查看是否命中某一战法。

```bash
python src/stock_trade_z/check_code.py \
  --out ./data \
  --symbol 002594
```

**参数说明**

| 参数         | 默认值 | 说明                    |
| ------------ | ------ | ----------------------- |
| `--data-dir` | 必填   | K线行情目录             |
| `--symbol`   | 必填   | 需要检查的股票代码，6位 |

### 5. 添加股票到优选列表

将新的股票代码添加到 `stocklist.good.csv` 文件中。

```bash
python src/stock_trade_z/update_to_goodlist.py \
  --stocklist ./stocklist.good.csv
```

**参数说明**

| 参数          | 默认值 | 说明                  |
| ------------- | ------ | --------------------- |
| `--stocklist` | 必填   | 股票列表 CSV 文件路径 |

---

## 内置策略（Selector）

> **提示**：文中“窗口”均指交易日数量。实际实现均已替换为最新代码逻辑。

### 1. BBIKDJSelector（少妇战法）

核心逻辑：

- **价格波动约束**：最近 `max_window` 根收盘价的波动（`high/low-1`）≤ `price_range_pct`；
- **BBI 上升**：`bbi_deriv_uptrend`，允许一阶差分在 `bbi_q_threshold` 分位内为负（容忍回撤）；
- **KDJ 低位**：当日 J 值 **< `j_threshold`** 或 **≤ 最近 `max_window` 的 `j_q_threshold` 分位**；
- **MACD**：`DIF > 0`；
- **MA60 条件**：当日 `close ≥ MA60` 且最近 `max_window` 内存在“**有效上穿 MA60**”；
- **知行当日约束**：**收盘 > 长期线** 且 **短期线 > 长期线**。

`selector.config.json` 预设（与示例一致）：

```json
{
  "class": "BBIKDJSelector",
  "alias": "少妇战法",
  "activate": true,
  "params": {
    "j_threshold": 15,
    "bbi_min_window": 20,
    "max_window": 120,
    "price_range_pct": 1,
    "bbi_q_threshold": 0.2,
    "j_q_threshold": 0.1
  }
}
```

### 2. SuperB1Selector（SuperB1战法）

核心逻辑：

1. 在 `lookback_n` 窗内，存在某日 `t_m` **满足 BBIKDJSelector**；
2. 区间 `[t_m, 当日前一日]` 收盘价波动率 ≤ `close_vol_pct`；
3. 当日相对前一日 **下跌 ≥ `price_drop_pct`**；
4. 当日 J **< `j_threshold`** 或 **≤ `j_q_threshold` 分位**；
5. **知行约束**：
   - 在 `t_m` 当日：**收盘 > 长期线** 且 **短期线 > 长期线**；
   - 在 **当日**：只需 **短期线 > 长期线**。

`selector.config.json` 预设：

```json
{
  "class": "SuperB1Selector",
  "alias": "SuperB1战法",
  "activate": true,
  "params": {
    "lookback_n": 10,
    "close_vol_pct": 0.02,
    "price_drop_pct": 0.02,
    "j_threshold": 10,
    "j_q_threshold": 0.1,
    "B1_params": {
      "j_threshold": 15,
      "bbi_min_window": 20,
      "max_window": 120,
      "price_range_pct": 1,
      "bbi_q_threshold": 0.3,
      "j_q_threshold": 0.1
    }
  }
}
```

### 3. BBIShortLongSelector（补票战法）

核心逻辑：

- **BBI 上升**（容忍回撤）；
- 最近 `m` 日内：
  - 长 RSV（`n_long`）**全 ≥ `upper_rsv_threshold`**；
  - 短 RSV（`n_short`）出现“**先 ≥ upper，再 < lower**”的序列结构；
  - 当日短 RSV **≥ upper**；

- **MACD**：`DIF > 0`；
- **知行当日约束**：**收盘 > 长期线** 且 **短期线 > 长期线**。

`selector.config.json` 预设：

```json
{
  "class": "BBIShortLongSelector",
  "alias": "补票战法",
  "activate": true,
  "params": {
    "n_short": 5,
    "n_long": 21,
    "m": 5,
    "bbi_min_window": 2,
    "max_window": 120,
    "bbi_q_threshold": 0.2,
    "upper_rsv_threshold": 75,
    "lower_rsv_threshold": 25
  }
}
```

### 4. PeakKDJSelector（填坑战法）

核心逻辑：

- 基于 `open/close` 的 `oc_max` 寻找峰值（`scipy.signal.find_peaks`）；
- 选择最新峰 `peak_t` 与其前方**有效参照峰** `peak_(t-n)`：要求 `oc_t > oc_(t-n)`，并确保区间内其它峰不“抬高门槛”；且 `oc_(t-n)` 必须 **高于区间最低收盘价 `gap_threshold`**；
- 当日收盘与 `peak_(t-n)` 的波动率 ≤ `fluc_threshold`；
- 当日 J **< `j_threshold`** 或 **≤ `j_q_threshold` 分位**；
- **知行当日约束**：**收盘 > 长期线** 且 **短期线 > 长期线**。

`selector.config.json` 预设：

```json
{
  "class": "PeakKDJSelector",
  "alias": "填坑战法",
  "activate": true,
  "params": {
    "j_threshold": 10,
    "max_window": 120,
    "fluc_threshold": 0.03,
    "j_q_threshold": 0.1,
    "gap_threshold": 0.2
  }
}
```

### 5. MA60CrossVolumeWaveSelector（上穿60放量战法）

核心逻辑：

1. 当日 J **< `j_threshold`** 或 **≤ `j_q_threshold` 分位**；
2. 最近 `lookback_n` 内存在**有效上穿 MA60**；
3. 以上穿日 `T` 到当日区间内 **High 最大日** 作为 `Tmax`，定义上涨波段 `[T, Tmax]`，其 **平均成交量 ≥ `vol_multiple` × 上穿前等长或截断窗口的平均量**；
4. `MA60` 的最近 `ma60_slope_days` 日 **回归斜率 > 0**；
5. **知行当日约束**：**收盘 > 长期线** 且 **短期线 > 长期线**。

`selector.config.json` 预设：

```json
{
  "class": "MA60CrossVolumeWaveSelector",
  "alias": "上穿60放量战法",
  "activate": true,
  "params": {
    "lookback_n": 25,
    "vol_multiple": 1.8,
    "j_threshold": 15,
    "j_q_threshold": 0.1,
    "ma60_slope_days": 5,
    "max_window": 120
  }
}
```

> **已移除**：`BreakoutVolumeKDJSelector（TePu 战法）`。

### 6. BigBullishVolumeSelector（暴力K战法）

核心逻辑：

1. **当日为长阳**：
   当日涨幅 `(close / prev_close - 1)` **大于 `up_pct_threshold`**；

2. **上影线短**：
   上影线比例
   \[
   \frac{High - \max(Open, Close)}{\max(Open, Close)}
   \]
   **小于 `upper_wick_pct_max`**，用于过滤冲高回落型假阳线；

3. **放量突破**：
   当日成交量
   \[
   Volume\_{today} \ge vol_multiple \times \text{前 } n \text{ 日均量}
   \]

4. **贴近知行短线（不过热）**：
   计算 `ZXDQ = EMA(EMA(C,10),10)`，要求
   \[
   Close < ZXDQ \times close_lt_zxdq_mult
   \]
   用于过滤已经明显脱离短线均值、过度加速的股票。

5. （可选）**收阳约束**：`close ≥ open`。

该策略意在捕捉：

> **“刚刚放量启动的强势阳线，但尚未远离短期均线、仍具延续空间的个股”。**

---

`selector.config.json` 预设：

```json
{
  "class": "BigBullishVolumeSelector",
  "alias": "暴力K战法",
  "activate": true,
  "params": {
    "up_pct_threshold": 0.06,
    "upper_wick_pct_max": 0.02,
    "require_bullish_close": true,
    "close_lt_zxdq_mult": 1.15,
    "vol_lookback_n": 20,
    "vol_multiple": 2.5
  }
}
```

---

## 项目结构

```bash
.
├── .vscode/                          # VS Code 配置
│  ├── tasks.json                     # 任务配置（快捷运行脚本）
│  ├── launch.json                    # 调试配置
│  └── settings.json                  # 编辑器设置
│
├── src/stock_trade_z/                # 主程序目录
│  ├── fetch_stocklist.py             # 获取所有股票列表
│  ├── fetch_kline.py                 # 下载历史 K 线数据（前复权）
│  ├── select_stock.py                # 批量选股主入口
│  ├── check_code.py                  # 检查单只股票是否命中战法
│  ├── update_to_goodlist.py             # 添加股票到优选列表
│  ├── sort_csv.py                    # 排序股票列表 CSV 文件
│  ├── try_play.py                    # 测试脚本
│  ├── add_xueqiu_urls.py             # 添加雪球链接
│  │
│  ├── selector.config.json           # 选股策略（selectors + quant_selectors）
│  ├── risk.config.json               # 风险检测策略
│  ├── stocklist.total.csv            # 全量股票池（5000+ 只）
│  │
│  └── lib/                           # 内部工具库
│     ├── __init__.py
│     ├── ts_pro_api.py               # Tushare API 封装
│     ├── selector.py                 # Z 哥战法选择器
│     ├── quant_selectors.py          # 主流量化选股策略
│     ├── risk_selectors.py           # 风险检测选择器
│     ├── registry.py                 # JSON 配置加载公共逻辑
│     ├── fetch_data.py               # 数据抓取工具
│     ├── load_data.py                # 数据加载工具
│     ├── load_selector.py            # 选择器加载工具
│     ├── load_stocklist.py           # 股票列表加载工具
│     ├── logger.py                   # 日志工具
│     ├── paths.py                    # 路径管理
│     ├── time.py                     # 时间处理工具
│     ├── utils.py                    # 通用工具函数
│     ├── constant.py                 # 常量定义
│     └── xueqiu.py                   # 雪球相关工具
│
├── data/                             # K 线行情 CSV 输出目录
├── stocklist.good.csv                # 优选股票池（经过初步筛选）
├── .env.example                      # 环境变量配置示例
├── pyproject.toml                    # 项目与 uv 依赖
├── uv.lock                           # 锁定依赖版本
└── log/                              # 运行日志
```

---

## 选股机制（`select_stock.py`）

1. **`load_data_folder`**：从 `--data-dir` 读取每只股票的 CSV，归一化 `date`，确定交易日。
2. **`load_selectors`**：读取 `selector.config.json` 中的 `selectors`（Z 战法）与 `quant_selectors`（主流量化策略），按 `class` 动态实例化并全部运行。
3. **并行扫描**：每个 Selector 对全市场调用 `select(date, data)`，内部用 `parallel_select_helper` 多进程执行 `_passes_filters(hist)`。
4. **结果汇总**：命中代码与 `stocklist.total.csv` 合并名称/雪球链接，写日志；`--send-lark` 时推送飞书卡片。

新增 **quant_selectors**（`lib/quant_selectors.py`，可在配置中 `activate: false` 关闭）：

| 别名 | 类 | 思路 |
|------|-----|------|
| 动量因子 | `MomentumSelector` | ROC + 价格在 MA 上方 |
| MACD金叉 | `MACDGoldenCrossSelector` | DIF 上穿 DEA，柱状线走强 |
| 布林均值回归 | `BollingerMeanReversionSelector` | 触及下轨 + RSI 超卖 |
| 唐奇安突破 | `DonchianBreakoutSelector` | N 日高点突破 + 放量 |
| 双均线金叉 | `DualMAGoldenCrossSelector` | 短均线上穿长均线 |

---

## Risk Selectors (风险检测)

风险检测由 **`risk.config.json`** 驱动（`load_risk_selectors`），实现位于 `lib/risk_selectors.py`：

- **ATR Volatility**：相对波动率过高
- **RSI Extremes**：超买/超卖极端
- **MA Decline**：均线空头排列且长期均线走弱
- **Volume Selloff**：放量下跌
- **Drawdown**：相对近期高点回撤过大
- **Gap Down**：跳空低开
- **MACD Bearish**：MACD 死叉或空头动能
- **Top Trap**：CCI 超买 + 顶部陷阱信号

```bash
uv run stock-detect-risk --data-dir ./data
```

输出按命中风险条数聚合排序。

---

## 常见问题

**Q1：为什么抓取会“卡住很久”？**
可能命中 Tushare 频控或网络封禁。脚本检测到典型关键字（如“访问频繁/429/403”）时，会进入**长冷却（默认 600s）** 再重试。

**Q2：为什么不做增量合并？**
考虑采用增量更新会遇到前复权的问题，本版选择**每次全量覆盖写入**。

**Q3：创业板/科创板/北交所如何排除？**
运行时使用 `--exclude-boards gem star bj`，或按需选择其一/其二。
