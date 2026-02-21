"""
从价格反推交易日期
已知：开仓价、平仓价、RPS评级，通过 yfinance 历史数据定位具体交易日
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

import yfinance as yf
import pandas as pd
import numpy as np

# ============================================================
# 从 IWA + 图片提取的已知信息（确定部分）
# ============================================================
KNOWN_TRADES = [
    # (ticker, entry_price, exit_price, return_pct, rps, exit_type)
    ('OSS',  8.38,   9.68,   15.51,  99.0,    '止盈'),
    ('JNJ',  206.02, 241.15, 17.05,  88.711,  '止盈'),
    ('INTC', 46.44,  43.17,  -7.04,  94.459,  '止损'),
    # LLY 持仓中，止损990.52, 止盈1061.77
    ('LLY',  1017.24, None,  None,   70.58,   '持仓'),
    ('PL',   20.89,  23.4,   None,   None,    '止盈'),
    ('MRNA', 40.486, 45.9,   None,   None,    '?'),
    ('GOOG', 298.0,  324.0,  0.70,   None,    '?'),   # 注：0.70可能是涨幅%
    ('NEM',  114.0,  125.4,  9.4,    None,    '?'),
    ('UUUU', 80.3,   85.75,  10.7,   None,    '?'),
]

def find_date_by_price(ticker, target_price, price_type='open', tolerance=0.02, lookback_days=500):
    """
    在历史数据中找到价格最接近 target_price 的日期
    price_type: 'open' | 'close' | 'low' | 'high'
    tolerance: 允许误差比例
    """
    tk = yf.Ticker(ticker)
    df = tk.history(period=f"{lookback_days}d", auto_adjust=True)
    if df.empty:
        return None, None

    col = price_type.capitalize()
    if col not in df.columns:
        col = 'Close'

    diff = (df[col] - target_price).abs() / target_price
    best_idx = diff.idxmin()
    best_diff = diff.min()

    if best_diff <= tolerance:
        return best_idx, df.loc[best_idx, col]
    return None, None


def reconstruct_trades():
    print("=" * 60)
    print("🔍 反推交易日期（通过价格匹配）")
    print("=" * 60)

    results = []
    for ticker, entry, exit_p, ret_pct, rps, exit_type in KNOWN_TRADES:
        print(f"\n--- {ticker} ---")
        if entry:
            entry_date, entry_actual = find_date_by_price(ticker, entry, 'open', tolerance=0.025)
            if entry_date is None:
                entry_date, entry_actual = find_date_by_price(ticker, entry, 'close', tolerance=0.025)
            print(f"  开仓 {entry}: 匹配日期={entry_date}, 实际价={entry_actual}")
        else:
            entry_date = None

        if exit_p:
            exit_date, exit_actual = find_date_by_price(ticker, exit_p, 'close', tolerance=0.025)
            if exit_date is None:
                exit_date, exit_actual = find_date_by_price(ticker, exit_p, 'open', tolerance=0.025)
            print(f"  平仓 {exit_p}: 匹配日期={exit_date}, 实际价={exit_actual}")
        else:
            exit_date = None

        results.append({
            'ticker': ticker,
            'entry_price': entry,
            'exit_price': exit_p,
            'return_pct': ret_pct,
            'rps': rps,
            'exit_type': exit_type,
            'entry_date_est': str(entry_date)[:10] if entry_date else None,
            'exit_date_est': str(exit_date)[:10] if exit_date else None,
        })

    df = pd.DataFrame(results)
    df.to_csv('/Users/vvusu/work/stock-strategy/data/raw/reconstructed_trades.csv', index=False)
    print(f"\n✅ 已保存: data/raw/reconstructed_trades.csv")
    print(df[['ticker','entry_price','exit_price','return_pct','rps','exit_type','entry_date_est','exit_date_est']].to_string(index=False))
    return df


if __name__ == '__main__':
    reconstruct_trades()
