"""
P3：回测分层验证 - 按市场环境(牛/熊/震荡)分别统计胜率

为什么要做这个？
  当前策略在不同市场状态下的表现差异可能非常大：
  - 牛市中「超卖买入」成功率高（大盘托底）
  - 熊市中同样信号胜率可能低至 30%（接飞刀）
  这个回测验证「市场环境过滤」是否真的有必要，
  以及各环境下的最优阈值应该是多少。

数据：1H，730天（yfinance 限制）
标的：核心持仓 + Tier2 关注池（共 18 只）
"""
import warnings
warnings.filterwarnings('ignore')

import sys, json, os
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

from analyzer.indicators import add_all_indicators


# ── 配置 ─────────────────────────────────────────────────────────────────────
TICKERS = [
    'TSLA','META','CRWD','PANW','ORCL','RKLB','OKLO','SOUN',
    'SNOW','ARM','AMD','NNE','SOFI','DXYZ','ASTS','IONQ',
    'GOOGL','NVDA',
]

TP_NORMAL = 0.13
SL_NORMAL = -0.08
TP_STRONG = 0.20
SL_STRONG = -0.08
STRONG_SCORE = 85
HOLD_MAX_BARS = 30 * 7


# ── 市场环境分类 ──────────────────────────────────────────────────────────────
def classify_regime(spy_close: pd.Series, idx: int) -> str:
    """
    对每个时间点分类市场状态（用历史数据，避免未来函数）
    需要至少 50 个交易日的 SPY 数据
    """
    if idx < 50:
        return 'unknown'

    window = spy_close.iloc[max(0, idx-200):idx+1]
    price  = float(spy_close.iloc[idx])
    ma50   = float(window.rolling(50).mean().iloc[-1])  if len(window) >= 50  else price
    ma200  = float(window.rolling(200).mean().iloc[-1]) if len(window) >= 200 else price

    # 近 20 日涨跌幅
    ret20  = float((price / spy_close.iloc[max(0, idx-20)] - 1) * 100) if idx >= 20 else 0

    if price > ma50 > ma200 and ret20 > -2:
        return 'bull'
    elif price < ma200 and ret20 < -5:
        return 'bear'
    else:
        return 'neutral'


def compute_score(row: pd.Series) -> int:
    """简化版评分（与 backtest_1h.py 一致）"""
    score = 50
    if row.get('above_ma200', 0) == 1:
        score += 15
    else:
        score -= 15
    if row.get('above_ma50', 0) == 1:
        score += 8
    rsi = row.get('rsi14', 50)
    if rsi < 25:    score += 20
    elif rsi < 35:  score += 12
    elif rsi < 45:  score += 6
    elif rsi > 65:  score -= 8
    ret5 = row.get('ret_5d', 0)
    if ret5 < -0.06:   score += 12
    elif ret5 < -0.03: score += 8
    macd_h = row.get('macd_hist', 0)
    if macd_h > 0:  score += 6
    else:           score -= 4
    return int(max(0, min(100, score)))


# ── 单股回测 ─────────────────────────────────────────────────────────────────
def backtest_one(ticker: str, spy_1d: pd.Series, period='730d') -> pd.DataFrame:
    df = yf.Ticker(ticker).history(period=period, interval='1h', auto_adjust=True)
    if df is None or len(df) < 400:
        return pd.DataFrame()
    df = df.copy()
    df.index = df.index.tz_convert(None)
    df.columns = [c.lower() for c in df.columns]
    df = add_all_indicators(df)

    trades = []
    in_trade = False

    for i in range(250, len(df)):
        row = df.iloc[i]
        price = float(row['close'])
        bar_time = df.index[i]

        # 找当前时间对应的 SPY 日线 index（向前找最近一根）
        spy_idx = spy_1d.index.searchsorted(bar_time.date().isoformat()) - 1
        spy_idx = max(0, min(spy_idx, len(spy_1d) - 1))
        regime = classify_regime(spy_1d, spy_idx)

        if not in_trade:
            if row.get('above_ma200', 0) != 1:
                continue
            rsi = float(row.get('rsi14', 99))
            ret5 = float(row.get('ret_5d', 0))
            if not (rsi < 45 and ret5 < -0.03):
                continue

            score = compute_score(row)
            is_strong = score >= STRONG_SCORE
            tp = TP_STRONG if is_strong else TP_NORMAL
            sl = SL_STRONG if is_strong else SL_NORMAL

            in_trade = True
            entry_i = i
            entry_price = price
            entry_time = bar_time
            entry_regime = regime
            entry_score = score
            entry_mode = 'strong' if is_strong else 'normal'
            tp_price = entry_price * (1 + tp)
            sl_price = entry_price * (1 + sl)

        else:
            bars = i - entry_i
            cur = float(df.iloc[i]['close'])
            exit_reason = None
            if cur >= tp_price:          exit_reason = 'TP'
            elif cur <= sl_price:        exit_reason = 'SL'
            elif bars >= HOLD_MAX_BARS:  exit_reason = 'TIME'

            if exit_reason:
                ret = (cur - entry_price) / entry_price
                trades.append({
                    'ticker':       ticker,
                    'entry_time':   entry_time,
                    'exit_time':    df.index[i],
                    'entry_price':  round(entry_price, 4),
                    'exit_price':   round(cur, 4),
                    'return_pct':   round(ret * 100, 2),
                    'bars':         bars,
                    'mode':         entry_mode,
                    'entry_score':  entry_score,
                    'exit_reason':  exit_reason,
                    'regime':       entry_regime,   # 入场时的市场环境
                    'is_win':       ret > 0,
                })
                in_trade = False

    return pd.DataFrame(trades)


def summarize(trades: pd.DataFrame, label: str = '') -> dict:
    if trades.empty:
        return {'label': label, 'count': 0}
    wins = trades[trades['return_pct'] > 0]
    loss = trades[trades['return_pct'] <= 0]
    pf = (wins['return_pct'].sum() / abs(loss['return_pct'].sum())) \
         if len(loss) and abs(loss['return_pct'].sum()) > 1e-9 else np.inf
    return {
        'label':         label,
        'count':         int(len(trades)),
        'win_rate':      round(len(wins) / len(trades) * 100, 2),
        'avg_win_pct':   round(float(wins['return_pct'].mean()), 2) if len(wins) else 0,
        'avg_loss_pct':  round(float(loss['return_pct'].mean()), 2) if len(loss) else 0,
        'expectancy':    round(float(trades['return_pct'].mean()), 3),
        'profit_factor': round(float(pf), 3) if pf != np.inf else 'inf',
        'tp_rate':       round(float((trades['exit_reason'] == 'TP').mean() * 100), 2),
        'sl_rate':       round(float((trades['exit_reason'] == 'SL').mean() * 100), 2),
    }


def run():
    print(f"📊 P3 回测分层验证 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  标的：{len(TICKERS)} 只 | 周期：1H / 730天\n")

    # 获取 SPY 日线（用于 regime 分类）
    print("  获取 SPY 日线...")
    spy_hist = yf.Ticker('SPY').history(period='730d', interval='1d', auto_adjust=True)
    spy_close_1d = spy_hist['Close'].copy()
    spy_close_1d.index = pd.to_datetime([str(d.date()) for d in spy_close_1d.index])

    # 逐股回测
    all_trades = []
    for t in TICKERS:
        try:
            print(f"  回测 {t}...", end=' ')
            tr = backtest_one(t, spy_close_1d)
            if not tr.empty:
                all_trades.append(tr)
                print(f"→ {len(tr)} 笔交易")
            else:
                print("→ 数据不足")
        except Exception as e:
            print(f"→ 失败: {e}")

    if not all_trades:
        print("无交易数据")
        return

    trades = pd.concat(all_trades, ignore_index=True)
    print(f"\n  总计：{len(trades)} 笔交易\n")

    # ── 分层统计 ─────────────────────────────────────────────
    results = {
        'generated_at': datetime.now().isoformat(),
        'total':        summarize(trades, '总体'),
        'by_regime':    {},
        'by_mode':      {},
        'regime_mode':  {},
    }

    print("=== 按市场环境分层 ===")
    for regime in ['bull', 'neutral', 'bear', 'unknown']:
        sub = trades[trades['regime'] == regime]
        s = summarize(sub, regime)
        results['by_regime'][regime] = s
        if s['count'] > 0:
            print(f"  [{regime:>7}] 笔数={s['count']:>4} | 胜率={s['win_rate']:>6.2f}% | "
                  f"期望={s['expectancy']:>+6.3f}% | PF={str(s['profit_factor']):>6}")

    print("\n=== 按信号模式分层 ===")
    for mode in ['normal', 'strong']:
        sub = trades[trades['mode'] == mode]
        s = summarize(sub, mode)
        results['by_mode'][mode] = s
        if s['count'] > 0:
            print(f"  [{mode:>6}] 笔数={s['count']:>4} | 胜率={s['win_rate']:>6.2f}% | "
                  f"期望={s['expectancy']:>+6.3f}% | PF={str(s['profit_factor']):>6}")

    print("\n=== 环境×模式交叉分析 ===")
    for regime in ['bull', 'neutral', 'bear']:
        for mode in ['normal', 'strong']:
            sub = trades[(trades['regime'] == regime) & (trades['mode'] == mode)]
            s = summarize(sub, f"{regime}_{mode}")
            results['regime_mode'][f"{regime}_{mode}"] = s
            if s['count'] > 0:
                print(f"  [{regime:>7}×{mode:<6}] 笔数={s['count']:>3} | "
                      f"胜率={s['win_rate']:>6.2f}% | 期望={s['expectancy']:>+6.3f}%")

    # 保存
    os.makedirs('data/processed', exist_ok=True)
    out_path = 'data/processed/backtest_regime_summary.json'
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    trades.to_csv('data/processed/backtest_regime_trades.csv', index=False)
    print(f"\n✅ 已保存：{out_path}")

    # 输出关键结论
    print("\n" + "="*60)
    print("📌 关键结论（用于优化市场环境过滤阈值）")
    print("="*60)
    for regime, label in [('bull','牛市'), ('neutral','震荡'), ('bear','熊市')]:
        s = results['by_regime'].get(regime, {})
        if s.get('count', 0) > 0:
            suggestion = (
                '✅ 正常发信号' if s['win_rate'] >= 55 else
                '⚠️ 提高阈值至80+' if s['win_rate'] >= 45 else
                '🚫 建议停发/阈值90+'
            )
            print(f"  {label}: 胜率{s['win_rate']:.1f}% | 期望{s['expectancy']:+.3f}% → {suggestion}")

    return results


if __name__ == '__main__':
    run()
