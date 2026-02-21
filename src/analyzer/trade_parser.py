"""
交易记录解析模块
把用户提供的交易记录标准化成 DataFrame
支持多种输入格式
"""

import pandas as pd
import numpy as np
from datetime import datetime


REQUIRED_COLS = ['ticker', 'entry_date', 'entry_price', 'exit_date', 'exit_price']


def parse_trades(raw) -> pd.DataFrame:
    """
    将原始交易数据标准化
    raw: list of dict / pd.DataFrame / CSV文件路径
    """
    if isinstance(raw, str):
        df = pd.read_csv(raw)
    elif isinstance(raw, list):
        df = pd.DataFrame(raw)
    elif isinstance(raw, pd.DataFrame):
        df = raw.copy()
    else:
        raise ValueError("raw 必须是 list/DataFrame/CSV路径")

    # 列名标准化（大小写/中英文兼容）
    col_map = {
        # 中文列名映射
        '股票代码': 'ticker', '代码': 'ticker', 'symbol': 'ticker',
        '买入日期': 'entry_date', '建仓日期': 'entry_date', 'buy_date': 'entry_date',
        '买入价格': 'entry_price', '建仓价': 'entry_price', 'buy_price': 'entry_price',
        '卖出日期': 'exit_date', '平仓日期': 'exit_date', 'sell_date': 'exit_date',
        '卖出价格': 'exit_price', '平仓价': 'exit_price', 'sell_price': 'exit_price',
        '方向': 'direction', '类型': 'exit_type', '备注': 'note',
        '盈亏': 'pnl', '收益率': 'return_pct',
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
    df.columns = df.columns.str.lower().str.strip()

    # 日期解析
    for col in ['entry_date', 'exit_date']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])

    # 价格数值化
    for col in ['entry_price', 'exit_price']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # 自动计算收益率（如果没有）
    if 'return_pct' not in df.columns:
        if {'entry_price', 'exit_price'}.issubset(df.columns):
            df['return_pct'] = (df['exit_price'] - df['entry_price']) / df['entry_price'] * 100

    # 持仓天数
    if {'entry_date', 'exit_date'}.issubset(df.columns):
        df['hold_days'] = (df['exit_date'] - df['entry_date']).dt.days

    # 盈亏分类
    if 'return_pct' in df.columns:
        df['is_win'] = df['return_pct'] > 0

    df = df.sort_values('entry_date').reset_index(drop=True)
    df['trade_id'] = df.index + 1

    return df


def trade_summary(df: pd.DataFrame) -> dict:
    """基础统计"""
    total = len(df)
    wins  = df['is_win'].sum() if 'is_win' in df.columns else 0

    return {
        'total_trades': total,
        'win_trades':   int(wins),
        'loss_trades':  int(total - wins),
        'win_rate':     round(wins / total * 100, 1) if total else 0,
        'avg_return':   round(df['return_pct'].mean(), 2) if 'return_pct' in df.columns else None,
        'avg_win':      round(df[df['is_win']]['return_pct'].mean(), 2) if wins else None,
        'avg_loss':     round(df[~df['is_win']]['return_pct'].mean(), 2) if (total - wins) else None,
        'avg_hold_days':round(df['hold_days'].mean(), 1) if 'hold_days' in df.columns else None,
        'max_win':      round(df['return_pct'].max(), 2) if 'return_pct' in df.columns else None,
        'max_loss':     round(df['return_pct'].min(), 2) if 'return_pct' in df.columns else None,
        'tickers':      sorted(df['ticker'].unique().tolist()) if 'ticker' in df.columns else [],
    }


def enrich_trades(trades_df: pd.DataFrame, market_data: dict) -> pd.DataFrame:
    """
    将交易记录与市场数据合并，
    在买入/卖出时刻快照技术指标
    market_data: {ticker: DataFrame(带技术指标)}
    """
    enriched = []

    for _, row in trades_df.iterrows():
        ticker = row['ticker']
        if ticker not in market_data:
            enriched.append(row.to_dict())
            continue

        mdf = market_data[ticker]

        def snap(date, prefix):
            """取最近一个交易日的指标快照"""
            try:
                idx = mdf.index.get_indexer([date], method='ffill')[0]
                if idx < 0:
                    return {}
                row_snap = mdf.iloc[idx]
                return {f'{prefix}_{k}': v for k, v in row_snap.items()}
            except Exception:
                return {}

        entry_snap = snap(row['entry_date'], 'entry')
        exit_snap  = snap(row['exit_date'],  'exit')

        enriched.append({**row.to_dict(), **entry_snap, **exit_snap})

    return pd.DataFrame(enriched)
