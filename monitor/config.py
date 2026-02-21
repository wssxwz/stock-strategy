"""
监控系统配置文件
"""

# ── 股票池（等待女王填充）──
WATCHLIST = [
    # S&P 500 股票池（501只，来源：格格list CSV，排除BRK.B/BF.B）
    'IDXX', 'MLM', 'BEN', 'EMN', 'FFIV', 'WSM', 'TSN', 'SMCI',
    'IR', 'RMD', 'APH', 'TTD', 'TPR', 'PCG', 'MPWR', 'NEM',
    'VMC', 'CEG', 'PLTR', 'AVGO', 'L', 'MSCI', 'MCO', 'SBUX',
    'AMD', 'CNC', 'TYL', 'PAYC', 'BBY', 'ALGN', 'SRE', 'GOOG',
    'GOOGL', 'NVDA', 'ROST', 'KLAC', 'ORCL', 'RL', 'VICI', 'APO',
    'PTC', 'TTWO', 'LOW', 'MMM', 'VST', 'KMB', 'CPAY', 'SPGI',
    'LYV', 'CF', 'MOH', 'DIS', 'AAPL', 'MSFT', 'MSI', 'GS',
    'MNST', 'GLW', 'NRG', 'EXPE', 'DELL', 'RJF', 'HIG', 'LIN',
    'ANET', 'CSGP', 'SYF', 'ZTS', 'DASH', 'TROW', 'TRGP', 'EL',
    'CCL', 'GE', 'CINF', 'ETR', 'FOXA', 'FOX', 'MU', 'TDG',
    'CRWD', 'WTW', 'NDAQ', 'HCA', 'BAX', 'CSCO', 'ADSK', 'KVUE',
    'MS', 'META', 'EPAM', 'PSX', 'HD', 'CAT', 'NCLH', 'PEG',
    'ZBRA', 'C', 'STZ', 'SNPS', 'UNH', 'INTU', 'SYK', 'MPC',
    'MTD', 'EIX', 'LH', 'FDS', 'COR', 'AMP', 'JBL', 'ATO',
    'PNR', 'MTB', 'NSC', 'DE', 'CAH', 'NTAP', 'ORLY', 'GEV',
    'ABT', 'REGN', 'BG', 'UHS', 'NI', 'ROL', 'TRV', 'CME',
    'ACN', 'ES', 'CDNS', 'XYZ', 'ODFL', 'TPL', 'WDAY', 'CHRW',
    'EVRG', 'IVZ', 'GEN', 'KEYS', 'D', 'CMI', 'TJX', 'SPG',
    'GPC', 'TRMB', 'CTAS', 'EBAY', 'TSCO', 'SOLV', 'PNC', 'KMI',
    'HPQ', 'CLX', 'DDOG', 'TAP', 'CSX', 'AKAM', 'JPM', 'KKR',
    'VLTO', 'LNT', 'PWR', 'COF', 'JKHY', 'AZO', 'WRB', 'XYL',
    'TEL', 'GRMN', 'EA', 'EXC', 'EFX', 'VTRS', 'GL', 'O',
    'BK', 'LRCX', 'BDX', 'APD', 'AXP', 'ALL', 'PPL', 'FITB',
    'MAA', 'KIM', 'ROK', 'ELV', 'CNP', 'DVA', 'ICE', 'AME',
    'AEP', 'V', 'UNP', 'STT', 'CTRA', 'FTNT', 'ETN', 'HON',
    'MCK', 'TFC', 'NWSA', 'PNW', 'UAL', 'WMB', 'HBAN', 'WELL',
    'SJM', 'HAS', 'ULTA', 'IT', 'ABNB', 'WMT', 'ERIE', 'LVS',
    'MA', 'DUK', 'XEL', 'PKG', 'BR', 'OKE', 'SCHW', 'DTE',
    'HSIC', 'F', 'COP', 'PH', 'PODD', 'KR', 'CBRE', 'MCHP',
    'HUBB', 'RF', 'ZBH', 'EXPD', 'ECL', 'BXP', 'CDW', 'PPG',
    'CTSH', 'NWS', 'JBHT', 'GEHC', 'RTX', 'URI', 'MAR', 'EQR',
    'MOS', 'MCD', 'ITW', 'DGX', 'AEE', 'CTVA', 'VLO', 'MHK',
    'BLK', 'GPN', 'AIZ', 'ADP', 'SWK', 'ROP', 'FE', 'PSA',
    'VTR', 'UPS', 'UBER', 'AXON', 'ED', 'AMCR', 'WY', 'JNJ',
    'FIS', 'CPRT', 'WEC', 'TDY', 'ACGL', 'PHM', 'GDDY', 'CFG',
    'IFF', 'INCY', 'REG', 'LEN', 'ENPH', 'NOW', 'AIG', 'NTRS',
    'CRM', 'CMCSA', 'NFLX', 'DD', 'YUM', 'SO', 'COIN', 'AMAT',
    'NDSN', 'ALLE', 'VRTX', 'MTCH', 'WYNN', 'HST', 'DRI', 'ALB',
    'AVY', 'INTC', 'KEY', 'AON', 'STE', 'EQIX', 'BSX', 'FRT',
    'CAG', 'EOG', 'DG', 'EMR', 'AWK', 'GD', 'CMS', 'PRU',
    'HLT', 'USB', 'MKTX', 'DOV', 'WM', 'DAL', 'CI', 'TXN',
    'PYPL', 'SYY', 'NOC', 'MO', 'PAYX', 'APA', 'HAL', 'HII',
    'LULU', 'DHI', 'BRO', 'BX', 'MDT', 'WAB', 'JCI', 'LII',
    'MMC', 'FANG', 'FAST', 'HPE', 'TGT', 'SHW', 'BAC', 'IRM',
    'ADI', 'BKR', 'POOL', 'LHX', 'DLTR', 'IPG', 'CBOE', 'GM',
    'COO', 'TKO', 'TMUS', 'CMG', 'PCAR', 'SWKS', 'MAS', 'J',
    'PGR', 'ADM', 'TSLA', 'GILD', 'DLR', 'OMC', 'NEE', 'AMGN',
    'HRL', 'GWW', 'FCX', 'WBA', 'BKNG', 'BALL', 'ISRG', 'PM',
    'MET', 'CRL', 'RSG', 'LMT', 'ARE', 'ABBV', 'RCL', 'A',
    'PLD', 'NVR', 'VRSN', 'AFL', 'HWM', 'CZR', 'IQV', 'COST',
    'DECK', 'PFG', 'KMX', 'PEP', 'EG', 'GNRC', 'NXPI', 'AJG',
    'HUM', 'HOLX', 'BIIB', 'CPT', 'EW', 'OTIS', 'SNA', 'FI',
    'INVH', 'K', 'SBAC', 'ADBE', 'PFE', 'FTV', 'ESS', 'GIS',
    'WDC', 'MGM', 'DAY', 'LDOS', 'EXR', 'PG', 'TXT', 'IBM',
    'AES', 'SW', 'CARR', 'IP', 'VZ', 'CB', 'AVB', 'BMY',
    'AOS', 'DVN', 'HSY', 'FSLR', 'FDX', 'WFC', 'DOC', 'EQT',
    'CVX', 'CPB', 'MKC', 'LKQ', 'STLD', 'WST', 'SLB', 'KO',
    'QCOM', 'TT', 'AMT', 'NUE', 'TMO', 'XOM', 'T', 'CCI',
    'OXY', 'MDLZ', 'VRSK', 'NKE', 'CL', 'CVS', 'LUV', 'RVTY',
    'MRNA', 'LLY', 'DPZ', 'CHTR', 'UDR', 'MRK', 'KDP', 'PANW',
    'EXE', 'BA', 'DHR', 'DOW', 'IEX', 'TER', 'AMZN', 'FICO',
    'APTV', 'TECH', 'STX', 'WBD', 'BLDR', 'LW', 'CHD', 'DXCM',
    'WAT', 'PARA', 'KHC', 'LYB', 'ON',
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
