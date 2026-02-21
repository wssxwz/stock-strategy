#!/usr/bin/env python3
"""
主入口 - 交易记录策略分析
用法:
  python analyze.py                    # 用示例数据测试
  python analyze.py trades.csv         # 指定交易记录文件
"""

import sys
import os
import pandas as pd

# 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from fetcher.market_data import fetch_ohlcv, save_cache, load_cache
from analyzer.indicators import add_all_indicators, add_crossover_signals
from analyzer.trade_parser import parse_trades, trade_summary, enrich_trades
from strategy.reverse_engineer import full_analysis


def load_market_data(tickers, start, end=None):
    """拉取并缓存市场数据 + 计算指标"""
    market_data = {}
    for ticker in tickers:
        print(f"  获取 {ticker} 数据...")
        df = load_cache(ticker)
        if df is None:
            df = fetch_ohlcv(ticker, start, end)
            save_cache(df, ticker)

        df = add_all_indicators(df)
        df = add_crossover_signals(df)
        market_data[ticker] = df

    return market_data


def run(trades_input):
    """完整分析流程"""

    # 1. 解析交易记录
    print("\n📂 解析交易记录...")
    trades = parse_trades(trades_input)
    print(f"   共 {len(trades)} 笔交易")

    summary = trade_summary(trades)
    print(f"\n📊 基础统计:")
    for k, v in summary.items():
        if k != 'tickers':
            print(f"   {k}: {v}")
    print(f"   涉及股票: {', '.join(summary['tickers'])}")

    # 2. 拉取市场数据
    tickers = summary['tickers']
    start = trades['entry_date'].min().strftime('%Y-%m-%d')
    end   = trades['exit_date'].max().strftime('%Y-%m-%d')
    print(f"\n📡 拉取市场数据 ({start} ~ {end})...")
    market_data = load_market_data(tickers, start, end)

    # 3. 富化交易数据（快照技术指标）
    print("\n🔗 合并技术指标快照...")
    enriched = enrich_trades(trades, market_data)
    enriched.to_csv('data/processed/enriched_trades.csv', index=False)
    print(f"   已保存: data/processed/enriched_trades.csv")

    # 4. 策略逆向分析
    report = full_analysis(enriched)

    print("\n\n✅ 分析完成！结果已保存到 reports/ 目录")
    return enriched, report


# ==================== 示例数据（用于测试框架） ====================
EXAMPLE_TRADES = [
    # 格式: ticker, entry_date, entry_price, exit_date, exit_price
    # 这里放置从用户获取的真实交易记录
    # 示例占位:
    {'ticker': 'AAPL', 'entry_date': '2024-01-15', 'entry_price': 185.0,
     'exit_date': '2024-02-01', 'exit_price': 196.5},
    {'ticker': 'NVDA', 'entry_date': '2024-02-10', 'entry_price': 620.0,
     'exit_date': '2024-02-25', 'exit_price': 788.0},
    {'ticker': 'TSLA', 'entry_date': '2024-01-08', 'entry_price': 220.0,
     'exit_date': '2024-01-20', 'exit_price': 198.0},
]


if __name__ == '__main__':
    if len(sys.argv) > 1:
        trades_input = sys.argv[1]
    else:
        print("⚠️  未指定交易记录文件，使用示例数据")
        print("📌 请将真实交易记录放入 data/raw/trades.csv 后运行:")
        print("   python analyze.py data/raw/trades.csv\n")
        trades_input = EXAMPLE_TRADES

    enriched, report = run(trades_input)
