"""策略回测模块（旧版日线）

用还原出的规则在历史数据上验证胜率/收益。

⚠️ 与实盘/1H 回测逻辑保持一致的两点同步：
- RS_1Y 不再硬过滤（仅在极弱时过滤）：默认仅当 RS_1Y ≤ -10% 才拦截
- ret5 阈值按“全市场连续无信号”自动降级：L0=-3%, L1=-2.5%(>=20), L2=-2%(>=30)

出场：止盈+13% / 止损-8%
"""
import sys, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, 'src')

import yfinance as yf
import pandas as pd
import numpy as np
from analyzer.indicators import add_all_indicators, add_crossover_signals

# RS module (relative strength vs SPY)
try:
    from rs_strength import compute_rs_1y as compute_rs_1y_fn
except Exception:
    compute_rs_1y_fn = None


def ret5_entry_from_no_signal_streak(streak: int) -> float:
    """Map no-signal streak to ret5 entry threshold."""
    try:
        s = int(streak or 0)
    except Exception:
        s = 0
    if s >= 30:
        return RET5_L2
    if s >= 20:
        return RET5_L1
    return RET5_L0


# ── 策略参数（从逆向工程还原 + 与实盘同步的升级项）──
TAKE_PROFIT  = 0.13   # +13%
STOP_LOSS    = -0.08  # -8%
HOLD_MAX     = 30     # 最大持仓天数（超时平仓）
RSI_ENTRY    = 45     # RSI买入阈值

# ret5 动态降级（与 full_scan 同口径）
RET5_L0 = -0.03   # -3.0%
RET5_L1 = -0.025  # -2.5% (no-signal >=20)
RET5_L2 = -0.02   # -2.0% (no-signal >=30)

# RS_1Y：只过滤“极弱”，避免 AAPL 这类轻度跑输被直接归零
RS_1Y_FLOOR_DEFAULT = -10.0  # vs SPY, in percent


def backtest_ticker(
    ticker: str,
    start: str = '2023-01-01',
    end: str = None,
    *,
    no_signal_streak: int = 0,
    rs_1y_floor: float = RS_1Y_FLOOR_DEFAULT,
) -> pd.DataFrame:
    """单只股票回测

    no_signal_streak: 连续无信号次数，用于 ret5 动态降级。
    rs_1y_floor: RS_1Y 极弱过滤线（百分比，vs SPY）。
    """
    hist = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=True)
    if len(hist) < 100:
        return pd.DataFrame()

    hist.index = hist.index.tz_localize(None)
    hist.columns = [c.lower() for c in hist.columns]
    hist = add_all_indicators(hist)
    hist = add_crossover_signals(hist)

    # precompute RS_1Y once per ticker (avoid per-bar calls)
    rs_1y = -999.0
    if compute_rs_1y_fn is not None:
        try:
            rs_1y = float(compute_rs_1y_fn(ticker))
        except Exception:
            rs_1y = -999.0

    ret5_entry = ret5_entry_from_no_signal_streak(no_signal_streak)

    trades = []
    in_trade = False
    entry_idx = None

    for i in range(50, len(hist)):
        row = hist.iloc[i]

        if not in_trade:
            # ── 买入条件 ──
            rsi   = row.get('rsi14', 99)
            above200 = row.get('above_ma200', 0)
            above50  = row.get('above_ma50', 0)
            ret5  = row.get('ret_5d', 0)
            macd_h = row.get('macd_hist', 0)

            # RS_1Y：只在“极弱”时过滤（vs SPY，百分比口径）
            rs_ok = (rs_1y == -999.0) or (rs_1y > rs_1y_floor)

            buy_signal = (
                above200 == 1 and
                rsi < RSI_ENTRY and
                ret5 < ret5_entry and
                rs_ok and
                macd_h < 0
            )

            if buy_signal:
                in_trade = True
                entry_idx = i
                entry_price = row['close']
                entry_date  = hist.index[i]
                entry_rsi   = rsi
                entry_ret5  = ret5 * 100
                entry_rs_1y = rs_1y

        else:
            # ── 出场条件 ──
            days_held = i - entry_idx
            current_ret = (hist.iloc[i]['close'] - entry_price) / entry_price

            exit_reason = None
            exit_price  = hist.iloc[i]['close']

            if current_ret >= TAKE_PROFIT:
                exit_reason = '止盈'
            elif current_ret <= STOP_LOSS:
                exit_reason = '止损'
            elif days_held >= HOLD_MAX:
                exit_reason = '超时'

            if exit_reason:
                trades.append({
                    'ticker':     ticker,
                    'entry_date': entry_date,
                    'exit_date':  hist.index[i],
                    'entry_price':round(entry_price, 2),
                    'exit_price': round(exit_price, 2),
                    'return_pct': round(current_ret * 100, 2),
                    'hold_days':  days_held,
                    'exit_reason':exit_reason,
                    'entry_rsi':  round(entry_rsi, 1),
                    'entry_ret5': round(entry_ret5, 1),
                    'ret5_entry': round(ret5_entry * 100, 1),
                    'entry_rs_1y': round(entry_rs_1y, 2),
                    'rs_1y_floor': float(rs_1y_floor),
                    'no_signal_streak': int(no_signal_streak),
                    'is_win':     current_ret > 0,
                })
                in_trade = False

    return pd.DataFrame(trades)


def run_backtest(tickers: list, start='2023-01-01') -> dict:
    """多股票批量回测"""
    all_trades = []
    print(f"\n🔁 开始回测 {len(tickers)} 只股票 (from {start})")
    print("=" * 60)

    for ticker in tickers:
        try:
            trades = backtest_ticker(ticker, start=start)
            if len(trades):
                all_trades.append(trades)
                wins = trades[trades['is_win']]
                lose = trades[~trades['is_win']]
                wr = len(wins)/len(trades)*100
                avg_r = trades['return_pct'].mean()
                print(f"  {ticker:<6} {len(trades):>3}笔  胜率{wr:>5.1f}%  均收益{avg_r:>+6.2f}%  "
                      f"盈{wins['return_pct'].mean():>+5.1f}%/亏{lose['return_pct'].mean():>+5.1f}%")
        except Exception as e:
            print(f"  {ticker}: ✗ {e}")

    if not all_trades:
        print("无回测结果")
        return {}

    df = pd.concat(all_trades, ignore_index=True)
    df.to_csv('data/processed/backtest_results.csv', index=False)

    wins = df[df['is_win']]
    lose = df[~df['is_win']]

    summary = {
        'total_trades': len(df),
        'win_trades':   len(wins),
        'loss_trades':  len(lose),
        'win_rate':     round(len(wins)/len(df)*100, 1),
        'avg_return':   round(df['return_pct'].mean(), 2),
        'avg_win':      round(wins['return_pct'].mean(), 2),
        'avg_loss':     round(lose['return_pct'].mean(), 2),
        'profit_factor':round(wins['return_pct'].sum() / abs(lose['return_pct'].sum()), 2),
        'avg_hold':     round(df['hold_days'].mean(), 1),
        'exit_dist':    df['exit_reason'].value_counts().to_dict(),
        'annual_trades':round(len(df) / ((pd.Timestamp.now() - pd.Timestamp(start)).days / 365), 0),
    }

    print(f"\n{'='*60}")
    print(f"📊 回测汇总 ({start} ~ 今日)")
    print(f"{'='*60}")
    print(f"  总交易笔数: {summary['total_trades']}")
    print(f"  胜率:       {summary['win_rate']}%")
    print(f"  平均收益:   {summary['avg_return']:+.2f}%/笔")
    print(f"  平均盈利:   {summary['avg_win']:+.2f}%  平均亏损: {summary['avg_loss']:+.2f}%")
    print(f"  盈亏比:     {summary['avg_win']/abs(summary['avg_loss']):.2f}:1")
    print(f"  利润因子:   {summary['profit_factor']}")
    print(f"  平均持仓:   {summary['avg_hold']}天")
    print(f"  出场分布:   {summary['exit_dist']}")
    print(f"  年化交易频次:{summary['annual_trades']:.0f}笔/年")
    print(f"\n  已保存: data/processed/backtest_results.csv")

    return summary, df


if __name__ == '__main__':
    # 用历史信号里出现过的股票回测
    TICKERS = [
        'OSS','JNJ','PL','MRNA','NEM','RTX','ISSC','LPTH','CLS',
        'ADEA','GDX','RKLB','ASTS','INTC','XME','HL',
        'NVDA','META','AMZN','GOOG','TSLA','PLTR','APP',
        'GS','IBKR','CELH','CRWD','AXON','NET','DDOG',
    ]
    summary, trades = run_backtest(TICKERS, start='2022-01-01')
