"""
完整44条交易记录
来源：格格list—1h信号 频道
信号发布者：Robby
"""

# 格式：(ticker, 类型, 开/平仓价, 止损, 止盈, 盈亏%, RPS, 买卖次序)
# 类型: 开仓/止盈/止损
# 买卖次序: 一买/二买

RAW_SIGNALS = [
    # --- 已平仓记录（有开仓价+平仓价+盈亏）---
    {"ticker": "OSS",  "action": "止盈", "order": "一买", "entry": 8.38,   "exit": 9.68,   "pnl": 15.51,  "rps": 99.0,    "tp": None,    "sl": None},
    {"ticker": "JNJ",  "action": "止盈", "order": "二买", "entry": 206.02, "exit": 241.15, "pnl": 17.05,  "rps": 88.711,  "tp": None,    "sl": None},
    {"ticker": "INTC", "action": "止损", "order": "一买", "entry": 46.44,  "exit": 43.17,  "pnl": -7.04,  "rps": 94.459,  "tp": None,    "sl": None},
    {"ticker": "PL",   "action": "止盈", "order": "一买", "entry": 20.89,  "exit": 23.42,  "pnl": 12.11,  "rps": 99.0,    "tp": None,    "sl": None},
    {"ticker": "MRNA", "action": "止盈", "order": "一买", "entry": 40.48,  "exit": 45.97,  "pnl": 13.58,  "rps": 98.0,    "tp": None,    "sl": None},
    {"ticker": "XME",  "action": "止损", "order": "一买", "entry": 121.1,  "exit": 112.18, "pnl": -7.37,  "rps": 94.577,  "tp": None,    "sl": None},
    {"ticker": "HL",   "action": "止损", "order": "一买", "entry": 22.8,   "exit": 20.66,  "pnl": -9.39,  "rps": 99.0,    "tp": None,    "sl": None},
    {"ticker": "LPTH", "action": "止盈", "order": "一买", "entry": 9.39,   "exit": 11.39,  "pnl": 21.3,   "rps": 99.0,    "tp": None,    "sl": None},
    {"ticker": "NEM",  "action": "止盈", "order": "一买", "entry": 114.58, "exit": 125.45, "pnl": 9.49,   "rps": 98.0,    "tp": None,    "sl": None},
    {"ticker": "RTX",  "action": "止盈", "order": "一买", "entry": 196.12, "exit": 201.74, "pnl": 2.87,   "rps": 88.369,  "tp": None,    "sl": None},
    {"ticker": "ISSC", "action": "止盈", "order": "一买", "entry": 18.54,  "exit": 21.55,  "pnl": 16.24,  "rps": 99.0,    "tp": None,    "sl": None},
    {"ticker": "ZETA", "action": "止损", "order": "一买", "entry": 16.23,  "exit": 14.78,  "pnl": -8.93,  "rps": 13.244,  "tp": None,    "sl": None},
    {"ticker": "RKLB", "action": "止损", "order": "一买", "entry": 73.16,  "exit": 63.9,   "pnl": -12.66, "rps": 98.0,    "tp": None,    "sl": None},
    {"ticker": "ASTS", "action": "止损", "order": "二买", "entry": 101.63, "exit": 83.95,  "pnl": -17.4,  "rps": 98.0,    "tp": None,    "sl": None},
    {"ticker": "ADEA", "action": "止盈", "order": "二买", "entry": 17.46,  "exit": 18.8,   "pnl": 7.67,   "rps": 87.458,  "tp": None,    "sl": None},
    {"ticker": "MRNA", "action": "止损", "order": "一买", "entry": 40.32,  "exit": 37.19,  "pnl": -7.78,  "rps": 88.732,  "tp": None,    "sl": None},
    {"ticker": "CLS",  "action": "止盈", "order": "一买", "entry": 275.45, "exit": 313.59, "pnl": 13.85,  "rps": 98.0,    "tp": None,    "sl": None},
    {"ticker": "1347", "action": "止损", "order": "一买", "entry": 103.5,  "exit": 95.05,  "pnl": -8.16,  "rps": 98.0,    "tp": None,    "sl": None},

    # --- 开仓信号（有止损/止盈位，尚未平仓）---
    {"ticker": "LLY",  "action": "开仓", "order": "一买", "entry": 1017.24,"exit": None,   "pnl": None,   "rps": 70.58,   "tp": 1061.77, "sl": 990.52},
    {"ticker": "HL",   "action": "开仓", "order": "一买", "entry": 23.13,  "exit": None,   "pnl": None,   "rps": 99.0,    "tp": 26.17,   "sl": 21.3},
    {"ticker": "OSS",  "action": "开仓", "order": "一买", "entry": 8.38,   "exit": None,   "pnl": None,   "rps": 98.0,    "tp": 9.77,    "sl": 7.54},
    {"ticker": "QQQ",  "action": "开仓", "order": "一买", "entry": 600.7,  "exit": None,   "pnl": None,   "rps": 57.142,  "tp": 620.96,  "sl": 588.55},
    {"ticker": "INTC", "action": "开仓", "order": "一买", "entry": 46.44,  "exit": None,   "pnl": None,   "rps": 97.816,  "tp": 50.83,   "sl": 43.81},
    {"ticker": "GOOG", "action": "开仓", "order": "一买", "entry": 307.97, "exit": None,   "pnl": None,   "rps": 90.707,  "tp": 324.55,  "sl": 298.02},
    {"ticker": "EOSE", "action": "开仓", "order": "二买", "entry": 11.34,  "exit": None,   "pnl": None,   "rps": 87.109,  "tp": 13.34,   "sl": 10.14},
    {"ticker": "HL",   "action": "开仓", "order": "一买", "entry": 22.8,   "exit": None,   "pnl": None,   "rps": 99.0,    "tp": 25.88,   "sl": 20.95},
    {"ticker": "RKLB", "action": "开仓", "order": "一买", "entry": 68.84,  "exit": None,   "pnl": None,   "rps": 98.0,    "tp": 79.29,   "sl": 62.57},
    {"ticker": "UAMY", "action": "开仓", "order": "一买", "entry": 7.68,   "exit": None,   "pnl": None,   "rps": 97.577,  "tp": 9.21,    "sl": 6.76},
    {"ticker": "IREN", "action": "开仓", "order": "一买", "entry": 42.85,  "exit": None,   "pnl": None,   "rps": 99.0,    "tp": 50.62,   "sl": 38.19},
    {"ticker": "PL",   "action": "开仓", "order": "一买", "entry": 20.89,  "exit": None,   "pnl": None,   "rps": 99.0,    "tp": 23.94,   "sl": 19.06},
    {"ticker": "MRNA", "action": "开仓", "order": "一买", "entry": 40.48,  "exit": None,   "pnl": None,   "rps": 92.673,  "tp": 46.28,   "sl": 36.99},
    {"ticker": "RTX",  "action": "开仓", "order": "一买", "entry": 196.12, "exit": None,   "pnl": None,   "rps": 86.243,  "tp": 203.2,   "sl": 191.87},
    {"ticker": "GDX",  "action": "开仓", "order": "一买", "entry": 97.91,  "exit": None,   "pnl": None,   "rps": 98.0,    "tp": 107.66,  "sl": 92.06},
    {"ticker": "SPX",  "action": "开仓", "order": "一买", "entry": 6878.17,"exit": None,   "pnl": None,   "rps": 66.663,  "tp": 7059.55, "sl": 6769.34},
    {"ticker": "TSLA", "action": "开仓", "order": "二买", "entry": 410.14, "exit": None,   "pnl": None,   "rps": 62.784,  "tp": 442.48,  "sl": 390.73},
    {"ticker": "XME",  "action": "开仓", "order": "一买", "entry": 121.1,  "exit": None,   "pnl": None,   "rps": 97.24,   "tp": 131.3,   "sl": 114.98},
    {"ticker": "GS",   "action": "开仓", "order": "二买", "entry": 927.67, "exit": None,   "pnl": None,   "rps": 88.457,  "tp": 992.23,  "sl": 888.94},
    {"ticker": "ZETA", "action": "开仓", "order": "一买", "entry": 16.23,  "exit": None,   "pnl": None,   "rps": 24.101,  "tp": 18.64,   "sl": 14.79},
    {"ticker": "NEM",  "action": "开仓", "order": "一买", "entry": 114.58, "exit": None,   "pnl": None,   "rps": 98.0,    "tp": 125.47,  "sl": 108.05},
    {"ticker": "POET", "action": "开仓", "order": "一买", "entry": 5.51,   "exit": None,   "pnl": None,   "rps": 52.682,  "tp": 6.39,    "sl": 4.98},
    {"ticker": "UUUU", "action": "开仓", "order": "一买", "entry": 20.29,  "exit": None,   "pnl": None,   "rps": 99.0,    "tp": 24.83,   "sl": 17.56},
    {"ticker": "IBKR", "action": "开仓", "order": "二买", "entry": 73.46,  "exit": None,   "pnl": None,   "rps": 85.75,   "tp": 80.37,   "sl": 69.31},
    {"ticker": "OSS",  "action": "开仓", "order": "二买", "entry": 8.92,   "exit": None,   "pnl": None,   "rps": 98.0,    "tp": 10.71,   "sl": 7.84},
    {"ticker": "UUUU", "action": "开仓", "order": "二买", "entry": 20.84,  "exit": None,   "pnl": None,   "rps": 99.0,    "tp": 25.28,   "sl": 18.18},
    {"ticker": "MRNA", "action": "开仓", "order": "一买", "entry": 40.32,  "exit": None,   "pnl": None,   "rps": 94.032,  "tp": 45.44,   "sl": 37.25},
]
