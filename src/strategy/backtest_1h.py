"""1H 回测（yfinance 限制：约 730 天）

目标：验证方案B（强趋势更大止盈目标）对绩效的影响
- 普通信号：TP +13% / SL -8%
- 强趋势：TP +20% / SL -8% （score>=85）

注意：
- 1H 数据是美东交易时段；回测用 close 作为成交价近似
- 采用逐根K线检查 TP/SL 命中，命中即出场
- 不考虑滑点/手续费
"""

import warnings
warnings.filterwarnings('ignore')

import sys
from datetime import datetime
from typing import List, Dict

import numpy as np
import pandas as pd
import yfinance as yf

# 允许直接运行：把 src/ 加入路径
sys.path.insert(0, 'src')
from analyzer.indicators import add_all_indicators


TP_NORMAL = 0.13
SL_NORMAL = -0.08
TP_STRONG = 0.20
SL_STRONG = -0.08
STRONG_SCORE = 85

# 进场条件（对齐 signal_engine 的核心思想：趋势过滤 + 低位 + 回调）
RSI_ENTRY = 45
RET5_ENTRY = -0.03

# 出场保护：最长持仓（按小时K）
HOLD_MAX_BARS = 30 * 7  # 约 30 个交易日 * 每天 ~7根（粗略）


def compute_score(row: pd.Series) -> int:
    """简化版评分（用于区分 strong/normal）

    说明：我们不复刻全量评分引擎（会引入更多依赖/数据），
    用可回测的技术面评分近似：
      - 趋势（MA200/MA50）
      - 超卖程度（RSI）
      - 回调幅度（ret_5d）
      - MACD 动能
    """
    score = 50

    if row.get('above_ma200', 0) == 1:
        score += 15
    else:
        score -= 15

    if row.get('above_ma50', 0) == 1:
        score += 8

    rsi = row.get('rsi14', 50)
    if rsi < 25:
        score += 20
    elif rsi < 35:
        score += 12
    elif rsi < 45:
        score += 6
    elif rsi > 65:
        score -= 8

    ret5 = row.get('ret_5d', 0)
    if ret5 < -0.06:
        score += 12
    elif ret5 < -0.03:
        score += 8

    macd_h = row.get('macd_hist', 0)
    if macd_h > 0:
        score += 6
    else:
        score -= 4

    return int(max(0, min(100, score)))


def fetch_1h(ticker: str, period: str = '730d') -> pd.DataFrame:
    df = yf.Ticker(ticker).history(period=period, interval='1h', auto_adjust=True)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    df.index = df.index.tz_convert(None)
    df.columns = [c.lower() for c in df.columns]
    return df


def backtest_ticker_1h(ticker: str, period='730d') -> pd.DataFrame:
    df = fetch_1h(ticker, period=period)
    if len(df) < 400:
        return pd.DataFrame()

    df = add_all_indicators(df)

    trades = []
    in_trade = False
    entry_i = None

    for i in range(250, len(df)):
        row = df.iloc[i]
        price = float(row['close'])

        if not in_trade:
            # 进场条件：MA200上 + RSI<45 + 5日回调<-3%
            if row.get('above_ma200', 0) != 1:
                continue
            rsi = float(row.get('rsi14', 99))
            ret5 = float(row.get('ret_5d', 0))
            if not (rsi < RSI_ENTRY and ret5 < RET5_ENTRY):
                continue

            score = compute_score(row)
            is_strong = score >= STRONG_SCORE

            tp = TP_STRONG if is_strong else TP_NORMAL
            sl = SL_STRONG if is_strong else SL_NORMAL

            in_trade = True
            entry_i = i
            entry_price = price
            entry_time = df.index[i]
            entry_score = score
            entry_mode = 'strong' if is_strong else 'normal'
            tp_price = entry_price * (1 + tp)
            sl_price = entry_price * (1 + sl)

        else:
            bars = i - entry_i
            cur = float(df.iloc[i]['close'])
            ret = (cur - entry_price) / entry_price

            exit_reason = None
            if cur >= tp_price:
                exit_reason = 'TP'
            elif cur <= sl_price:
                exit_reason = 'SL'
            elif bars >= HOLD_MAX_BARS:
                exit_reason = 'TIME'

            if exit_reason:
                trades.append({
                    'ticker': ticker,
                    'entry_time': entry_time,
                    'exit_time': df.index[i],
                    'entry_price': round(entry_price, 4),
                    'exit_price': round(cur, 4),
                    'return_pct': round(ret * 100, 2),
                    'bars': bars,
                    'mode': entry_mode,
                    'entry_score': entry_score,
                    'exit_reason': exit_reason,
                    'is_win': ret > 0,
                })
                in_trade = False

    return pd.DataFrame(trades)


def summarize(trades: pd.DataFrame) -> Dict:
    if trades.empty:
        return {'count': 0}

    wins = trades[trades['return_pct'] > 0]
    loss = trades[trades['return_pct'] <= 0]

    win_rate = len(wins) / len(trades)
    avg_win = wins['return_pct'].mean() if len(wins) else 0
    avg_loss = loss['return_pct'].mean() if len(loss) else 0

    pf = (wins['return_pct'].sum() / abs(loss['return_pct'].sum())) if len(loss) and abs(loss['return_pct'].sum()) > 1e-9 else np.inf

    return {
        'count': int(len(trades)),
        'win_rate': round(win_rate * 100, 2),
        'avg_win_pct': round(float(avg_win), 2) if len(wins) else 0,
        'avg_loss_pct': round(float(avg_loss), 2) if len(loss) else 0,
        'expectancy_pct': round(float(trades['return_pct'].mean()), 3),
        'profit_factor': round(float(pf), 3) if pf != np.inf else 'inf',
        'median_hold_bars': int(trades['bars'].median()),
        'tp_rate': round(float((trades['exit_reason'] == 'TP').mean() * 100), 2),
        'sl_rate': round(float((trades['exit_reason'] == 'SL').mean() * 100), 2),
        'time_rate': round(float((trades['exit_reason'] == 'TIME').mean() * 100), 2),
    }


def run(tickers: List[str], period='730d') -> Dict:
    all_trades = []
    for t in tickers:
        try:
            tr = backtest_ticker_1h(t, period=period)
            if not tr.empty:
                all_trades.append(tr)
        except Exception as e:
            print('ERR', t, e)

    trades = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()

    out = {
        'generated_at': datetime.now().isoformat(),
        'period': period,
        'tickers': tickers,
        'overall': summarize(trades),
        'normal': summarize(trades[trades['mode'] == 'normal']) if not trades.empty else {'count': 0},
        'strong': summarize(trades[trades['mode'] == 'strong']) if not trades.empty else {'count': 0},
    }
    return out, trades


if __name__ == '__main__':
    # 默认：关注池 + 核心持仓
    tickers = [
        'TSLA','GOOGL','NVDA','META',
        'RKLB','ASTS','PLTR','AMD','AVGO','LLY','AMZN','MSFT','AAPL','CRWD','NOW','DDOG','NEM','GDX'
    ]

    out, trades = run(tickers, period='730d')

    print('\n=== 1H 回测 (730d) 结果汇总 ===')
    print('总体:', out['overall'])
    print('普通:', out['normal'])
    print('强势:', out['strong'])

    # 保存
    import os, json
    os.makedirs('data/processed', exist_ok=True)
    with open('data/processed/backtest_1h_summary.json','w') as f:
        json.dump(out, f, indent=2)
    trades.to_csv('data/processed/backtest_1h_trades.csv', index=False)
    print('已保存: data/processed/backtest_1h_summary.json + backtest_1h_trades.csv')
