"""
监控系统配置文件
"""

# ── 股票池（等待女王填充）──
WATCHLIST = [
    # 粘贴你的股票列表到这里，例如：
    # 'NBIS', 'OKLO', 'RKLB', 'PLTR', ...
]

# ── 策略参数（基于逆向工程结果）──
STRATEGY = {
    # 买入条件
    'rsi_entry':       40,    # RSI < 40 视为低位（高波动股用30）
    'bb_entry':        0.35,  # BB% < 0.35 接近下轨
    'require_ma200':   True,  # 是否要求在MA200上方
    'require_macd_neg':True,  # 是否要求MACD柱为负

    # 出场参考（仅供通知，不自动下单）
    'take_profit':     0.13,  # 参考止盈 +13%
    'stop_loss':      -0.08,  # 参考止损 -8%

    # 扫描频率
    'scan_interval_min': 60,  # 每60分钟扫描一次

    # 美股交易时间（北京时间）
    'market_open_bj':  '21:30',
    'market_close_bj': '04:00',
}

# ── 通知配置（由 OpenClaw 自动处理）──
NOTIFY = {
    'channel': 'telegram',   # 通知渠道
    'min_score': 70,         # 最低评分才发通知（避免噪音）
}
