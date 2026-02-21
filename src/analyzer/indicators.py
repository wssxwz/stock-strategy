"""
技术指标计算模块
使用 ta 库，覆盖主流技术指标
"""

import pandas as pd
import numpy as np


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """在 OHLCV DataFrame 上添加所有常用技术指标"""
    df = df.copy()

    # -------- 均线 --------
    for n in [5, 10, 20, 50, 120, 200]:
        df[f'ma{n}'] = df['close'].rolling(n).mean()
        df[f'ema{n}'] = df['close'].ewm(span=n, adjust=False).mean()

    # -------- MACD --------
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']

    # -------- RSI --------
    for n in [6, 14, 21]:
        delta = df['close'].diff()
        gain = delta.clip(lower=0).rolling(n).mean()
        loss = (-delta.clip(upper=0)).rolling(n).mean()
        rs = gain / loss.replace(0, np.nan)
        df[f'rsi{n}'] = 100 - 100 / (1 + rs)

    # -------- Bollinger Bands --------
    for n in [20]:
        mid = df['close'].rolling(n).mean()
        std = df['close'].rolling(n).std()
        df[f'bb_mid{n}'] = mid
        df[f'bb_upper{n}'] = mid + 2 * std
        df[f'bb_lower{n}'] = mid - 2 * std
        df[f'bb_pct{n}'] = (df['close'] - df[f'bb_lower{n}']) / (df[f'bb_upper{n}'] - df[f'bb_lower{n}'])
        df[f'bb_width{n}'] = (df[f'bb_upper{n}'] - df[f'bb_lower{n}']) / mid

    # -------- ATR (波动率) --------
    for n in [14]:
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close  = (df['low']  - df['close'].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df[f'atr{n}'] = tr.rolling(n).mean()
        df[f'atr_pct{n}'] = df[f'atr{n}'] / df['close']  # 相对ATR

    # -------- KDJ --------
    low_n  = df['low'].rolling(9).min()
    high_n = df['high'].rolling(9).max()
    rsv = (df['close'] - low_n) / (high_n - low_n + 1e-9) * 100
    df['kdj_k'] = rsv.ewm(com=2, adjust=False).mean()
    df['kdj_d'] = df['kdj_k'].ewm(com=2, adjust=False).mean()
    df['kdj_j'] = 3 * df['kdj_k'] - 2 * df['kdj_d']

    # -------- Volume 指标 --------
    df['vol_ma5']  = df['volume'].rolling(5).mean()
    df['vol_ma20'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_ma20']  # 量比

    # -------- 价格位置 --------
    df['high_52w'] = df['high'].rolling(252).max()
    df['low_52w']  = df['low'].rolling(252).min()
    df['pct_from_52w_high'] = (df['close'] - df['high_52w']) / df['high_52w']
    df['pct_from_52w_low']  = (df['close'] - df['low_52w'])  / df['low_52w']

    # -------- 涨跌幅 --------
    for n in [1, 3, 5, 10, 20]:
        df[f'ret_{n}d'] = df['close'].pct_change(n)

    # -------- 趋势判断 --------
    df['above_ma20']  = (df['close'] > df['ma20']).astype(int)
    df['above_ma50']  = (df['close'] > df['ma50']).astype(int)
    df['above_ma200'] = (df['close'] > df['ma200']).astype(int)
    df['ma20_slope']  = df['ma20'].diff(5) / df['ma20'].shift(5)   # MA20 斜率

    # -------- K线形态 --------
    df['is_gap_up']   = (df['open'] > df['close'].shift(1)).astype(int)
    df['is_gap_down']  = (df['open'] < df['close'].shift(1)).astype(int)
    body = (df['close'] - df['open']).abs()
    candle_range = df['high'] - df['low']
    df['body_ratio'] = body / (candle_range + 1e-9)  # 实体占比

    return df


def add_crossover_signals(df: pd.DataFrame) -> pd.DataFrame:
    """添加金叉/死叉信号"""
    df = df.copy()

    # MA5/MA20 金叉死叉
    df['ma5_cross_ma20']  = np.where(
        (df['ma5'] > df['ma20']) & (df['ma5'].shift(1) <= df['ma20'].shift(1)), 1,
        np.where(
            (df['ma5'] < df['ma20']) & (df['ma5'].shift(1) >= df['ma20'].shift(1)), -1, 0
        )
    )

    # MACD 金叉死叉
    df['macd_cross'] = np.where(
        (df['macd'] > df['macd_signal']) & (df['macd'].shift(1) <= df['macd_signal'].shift(1)), 1,
        np.where(
            (df['macd'] < df['macd_signal']) & (df['macd'].shift(1) >= df['macd_signal'].shift(1)), -1, 0
        )
    )

    # RSI 超买超卖
    df['rsi14_oversold']  = (df['rsi14'] < 30).astype(int)
    df['rsi14_overbought'] = (df['rsi14'] > 70).astype(int)

    return df
