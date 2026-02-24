"""
相对强度模块（RS）
计算股票相对于 SPY 的强度，用于跨牛熊的趋势过滤

用法：
  from rs_strength import compute_rs_1y
  rs = compute_rs_1y('AAPL')  # 返回 AAPL 相对 SPY 的 1 年相对强度（%）
"""
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from functools import lru_cache

SPY_TICKER = 'SPY'
TRADING_DAYS_1Y = 252
CALENDAR_DAYS_1Y = 400  # ~252 trading days + weekends/holidays


@lru_cache(maxsize=500)
def get_spy_history(days: int = CALENDAR_DAYS_1Y) -> pd.DataFrame:
    """获取 SPY 历史数据（缓存）"""
    end = datetime.now()
    start = end - timedelta(days=days)
    df = yf.Ticker(SPY_TICKER).history(
        start=start.strftime('%Y-%m-%d'),
        end=(end + timedelta(days=1)).strftime('%Y-%m-%d'),
        interval='1d', auto_adjust=True
    )
    if df is None or df.empty:
        return pd.DataFrame()
    df.index = df.index.tz_localize(None) if df.index.tzinfo else df.index
    df.columns = [c.lower() for c in df.columns]
    return df


def compute_rs_1y(ticker: str) -> float:
    """
    计算 1 年相对强度（vs SPY）
    返回：stock_1y_return - spy_1y_return（百分比，例如 +5.2 表示跑赢 5.2%）
    """
    end = datetime.now()
    start = end - timedelta(days=CALENDAR_DAYS_1Y)

    try:
        stock_df = yf.Ticker(ticker).history(
            start=start.strftime('%Y-%m-%d'),
            end=(end + timedelta(days=1)).strftime('%Y-%m-%d'),
            interval='1d', auto_adjust=True
        )
    except Exception:
        return -999.0

    if stock_df is None or stock_df.empty or 'Close' not in stock_df.columns:
        return -999.0

    stock_df.index = stock_df.index.tz_localize(None) if stock_df.index.tzinfo else stock_df.index
    stock_df.columns = [c.lower() for c in stock_df.columns]

    spy_df = get_spy_history(CALENDAR_DAYS_1Y)
    if spy_df.empty or 'close' not in spy_df.columns:
        return -999.0

    # 对齐索引
    common_idx = stock_df.index.intersection(spy_df.index)
    if len(common_idx) < TRADING_DAYS_1Y + 10:
        return -999.0

    stock_close = stock_df.loc[common_idx, 'close']
    spy_close = spy_df.loc[common_idx, 'close']

    if len(stock_close) < TRADING_DAYS_1Y + 1:
        return -999.0

    stock_1y = float(stock_close.iloc[-1]) / float(stock_close.iloc[-TRADING_DAYS_1Y]) - 1
    spy_1y = float(spy_close.iloc[-1]) / float(spy_close.iloc[-TRADING_DAYS_1Y]) - 1

    rs = (stock_1y - spy_1y) * 100  # 转成百分比
    return round(rs, 2)


def compute_rs_multi(tickers: list, window: str = '1y') -> dict:
    """批量计算多只股票的 RS"""
    result = {}
    for t in tickers:
        if window == '1y':
            result[t] = compute_rs_1y(t)
    return result


if __name__ == '__main__':
    # 测试
    for t in ['AAPL', 'KO', 'TSLA', 'SPY']:
        rs = compute_rs_1y(t)
        print(f"{t}: RS_1Y = {rs:+.2f}%")
