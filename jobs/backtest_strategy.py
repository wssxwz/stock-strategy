"""Reusable backtest script (1H) for current strategy.

Goal
- Reproduce the exact backtest logic we used in chat (serial trades, no overlap).
- Make the *start bar / warm-up* deterministic so results don't drift (11 vs 12 trades).

Strategy (entry)
- above_ma200 == 1
- rsi14 < rsi_entry
- ret_5d < ret5_entry
- ret_1y > ret1y_min  (computed in-bar using lookback bars)
- macd_hist < 0

Exit
- take profit (tp_pct)
- stop loss (sl_pct)
- max holding bars (hold_max)

Data
- yfinance interval=1h, period=730d (max)
- auto_adjust=True

Usage examples
  python3 jobs/backtest_strategy.py --ticker TSLA
  python3 jobs/backtest_strategy.py --ticker TSLA --period 730d --out data/processed/tsla_trades.csv

Notes
- This script is intentionally *self-contained* (no dashboard side effects).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd
import yfinance as yf

# local imports
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from analyzer.indicators import add_all_indicators, add_crossover_signals


@dataclass
class Params:
    # entry
    rsi_entry: float = 45
    ret5_entry: float = -0.03
    ret1y_min: float = 0.20
    ret1y_lookback_bars: int = 1638  # ~252 trading days * 6.5 bars/day

    # exits
    tp_pct: float = 0.13
    sl_pct: float = -0.08
    hold_max: int = 195  # ~30 trading days * 6.5 bars/day

    # deterministic warmup
    warmup_bars: int = 300


def load_1h_history(ticker: str, period: str = "730d") -> pd.DataFrame:
    df = yf.Ticker(ticker).history(period=period, interval="1h", auto_adjust=True)
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.dropna().copy()
    # normalize index tz
    try:
        df.index = df.index.tz_convert(None)
    except Exception:
        pass

    df.columns = [c.lower() for c in df.columns]
    df = add_all_indicators(df)
    df = add_crossover_signals(df)
    return df


def compute_ret1y(df: pd.DataFrame, i: int, lookback: int) -> float:
    back = min(i, lookback)
    start_close = float(df["close"].iloc[i - back])
    cur_close = float(df["close"].iloc[i])
    if start_close == 0:
        return 0.0
    return (cur_close - start_close) / start_close


def entry_condition(df: pd.DataFrame, i: int, p: Params) -> Tuple[bool, Dict]:
    row = df.iloc[i]

    rsi = float(row.get("rsi14", 99))
    above200 = int(row.get("above_ma200", 0))
    above50 = int(row.get("above_ma50", 0))
    ret5 = float(row.get("ret_5d", 0))
    macd_h = float(row.get("macd_hist", 0))
    ret_1y = compute_ret1y(df, i, p.ret1y_lookback_bars)

    ok = (
        above200 == 1
        and rsi < p.rsi_entry
        and ret5 < p.ret5_entry
        and ret_1y > p.ret1y_min
        and macd_h < 0
    )

    meta = {
        "rsi14": rsi,
        "above_ma200": above200,
        "above_ma50": above50,
        "ret_5d_pct": ret5 * 100,
        "ret_1y_pct": ret_1y * 100,
        "macd_hist": macd_h,
    }
    return ok, meta


def backtest(df: pd.DataFrame, p: Params) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    trades: List[Dict] = []
    in_trade = False
    entry_i: Optional[int] = None
    entry_price: Optional[float] = None
    entry_time: Optional[pd.Timestamp] = None
    entry_meta: Dict = {}

    start_i = max(p.warmup_bars, p.ret1y_lookback_bars)  # deterministic start

    for i in range(start_i, len(df)):
        if not in_trade:
            ok, meta = entry_condition(df, i, p)
            if ok:
                in_trade = True
                entry_i = i
                entry_price = float(df["close"].iloc[i])
                entry_time = df.index[i]
                entry_meta = meta
        else:
            assert entry_i is not None and entry_price is not None and entry_time is not None
            bars_held = i - entry_i
            cur = float(df["close"].iloc[i])
            cur_ret = (cur - entry_price) / entry_price

            reason = None
            if cur_ret >= p.tp_pct:
                reason = "TP"
            elif cur_ret <= p.sl_pct:
                reason = "SL"
            elif bars_held >= p.hold_max:
                reason = "TIME"

            if reason:
                trades.append(
                    {
                        "entry_time": entry_time,
                        "exit_time": df.index[i],
                        "entry_price": round(entry_price, 2),
                        "exit_price": round(cur, 2),
                        "ret_pct": round(cur_ret * 100, 2),
                        "bars": int(bars_held),
                        "reason": reason,
                        **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in entry_meta.items()},
                    }
                )
                in_trade = False
                entry_i = None
                entry_price = None
                entry_time = None
                entry_meta = {}

    return pd.DataFrame(trades)


def summarize(trades: pd.DataFrame) -> Dict:
    if trades is None or trades.empty:
        return {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "total_return_serial": 0.0,
            "avg_ret_pct": 0.0,
            "median_ret_pct": 0.0,
            "avg_bars": 0.0,
            "exit_breakdown": {},
        }

    wins = int((trades["ret_pct"] > 0).sum())
    losses = int((trades["ret_pct"] <= 0).sum())

    equity = 1.0
    for r in trades["ret_pct"]:
        equity *= 1.0 + (float(r) / 100.0)

    return {
        "trades": int(len(trades)),
        "wins": wins,
        "losses": losses,
        "win_rate": wins / len(trades) if len(trades) else 0.0,
        "total_return_serial": equity - 1.0,
        "avg_ret_pct": float(trades["ret_pct"].mean()),
        "median_ret_pct": float(trades["ret_pct"].median()),
        "avg_bars": float(trades["bars"].mean()),
        "exit_breakdown": trades["reason"].value_counts().to_dict(),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--period", default="730d")
    ap.add_argument("--out", default="")

    ap.add_argument("--tp", type=float, default=0.13)
    ap.add_argument("--sl", type=float, default=-0.08)
    ap.add_argument("--hold", type=int, default=195)

    ap.add_argument("--rsi", type=float, default=45)
    ap.add_argument("--ret5", type=float, default=-0.03)
    ap.add_argument("--ret1y", type=float, default=0.20)

    ap.add_argument("--warmup", type=int, default=300)
    ap.add_argument("--ret1y_lookback", type=int, default=1638)

    args = ap.parse_args()

    p = Params(
        rsi_entry=args.rsi,
        ret5_entry=args.ret5,
        ret1y_min=args.ret1y,
        tp_pct=args.tp,
        sl_pct=args.sl,
        hold_max=args.hold,
        warmup_bars=args.warmup,
        ret1y_lookback_bars=args.ret1y_lookback,
    )

    df = load_1h_history(args.ticker, period=args.period)
    if df.empty:
        print(f"No data for {args.ticker}")
        return

    trades = backtest(df, p)
    stats = summarize(trades)

    print(f"\n{args.ticker} 1H backtest ({args.period})")
    print(f"Data range: {df.index.min()} -> {df.index.max()}")
    print(f"Trades: {stats['trades']}  Wins: {stats['wins']}  Losses: {stats['losses']}  WinRate: {stats['win_rate']*100:.2f}%")
    print(f"Total return (serial): {stats['total_return_serial']*100:.2f}%")
    print(f"Avg ret: {stats['avg_ret_pct']:.2f}%  Median: {stats['median_ret_pct']:.2f}%")
    print(f"Avg bars held: {stats['avg_bars']:.1f}")
    print(f"Exit breakdown: {stats['exit_breakdown']}")

    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        trades.to_csv(args.out, index=False)
        print(f"Saved trades to: {args.out}")


if __name__ == "__main__":
    main()
