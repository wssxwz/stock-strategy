"""
市场数据获取模块
支持: yfinance (免费, 美股)
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import os


def fetch_ohlcv(ticker: str, start: str, end: str = None, interval: str = "1d") -> pd.DataFrame:
    """
    拉取 OHLCV 数据
    :param ticker: 股票代码, e.g. 'AAPL'
    :param start:  开始日期 'YYYY-MM-DD'
    :param end:    结束日期 'YYYY-MM-DD', 默认今天
    :param interval: '1d' | '1h' | '15m' | '5m'
    """
    if end is None:
        end = datetime.today().strftime('%Y-%m-%d')

    # 提前多拉一些数据用于指标预热 (最多120天)
    start_dt = datetime.strptime(start, '%Y-%m-%d') - timedelta(days=120)
    start_prefetch = start_dt.strftime('%Y-%m-%d')

    tk = yf.Ticker(ticker)
    df = tk.history(start=start_prefetch, end=end, interval=interval, auto_adjust=True)

    if df.empty:
        raise ValueError(f"No data returned for {ticker}")

    df.index = pd.to_datetime(df.index)
    df.index = df.index.tz_localize(None) if df.index.tzinfo else df.index
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
    df.columns = ['open', 'high', 'low', 'close', 'volume']
    df.index.name = 'date'

    return df


def fetch_multi(tickers: list, start: str, end: str = None, interval: str = "1d") -> dict:
    """批量拉取多只股票"""
    result = {}
    for t in tickers:
        try:
            result[t] = fetch_ohlcv(t, start, end, interval)
            print(f"  ✓ {t}: {len(result[t])} rows")
        except Exception as e:
            print(f"  ✗ {t}: {e}")
    return result


def fetch_info(ticker: str) -> dict:
    """拉取股票基本信息"""
    tk = yf.Ticker(ticker)
    info = tk.info
    keys = ['shortName', 'sector', 'industry', 'marketCap', 'trailingPE',
            'forwardPE', 'priceToBook', 'beta', 'fiftyTwoWeekHigh', 'fiftyTwoWeekLow']
    return {k: info.get(k) for k in keys}


def save_cache(df: pd.DataFrame, ticker: str, cache_dir: str = "data/raw"):
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, f"{ticker}.csv")
    df.to_csv(path)
    print(f"Saved: {path}")


def load_cache(ticker: str, cache_dir: str = "data/raw") -> pd.DataFrame:
    path = os.path.join(cache_dir, f"{ticker}.csv")
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path, index_col='date', parse_dates=True)
    return df
