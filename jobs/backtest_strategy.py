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
import numpy as np

# local imports
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from analyzer.indicators import add_all_indicators, add_crossover_signals

# RS module (relative strength vs SPY)
try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
    from rs_strength import compute_rs_1y as compute_rs_1y_fn
except Exception:
    compute_rs_1y_fn = None


@dataclass
class Params:
    # entry
    rsi_entry: float = 45

    # ret5 dynamic downgrade (matches live scan)
    # L0: -3% (default)
    # L1: -2.5% when market has been "no-signal" for >=20 scans
    # L2: -2%   when market has been "no-signal" for >=30 scans (cap)
    ret5_entry: float = -0.03
    no_signal_streak: int = 0

    # RS_1Y: avoid hard-killing slightly-weak names like AAPL
    # Only filter out *extremely weak* names.
    rs_1y_floor: float = -10.0  # allow if RS_1Y > -10% (vs SPY)

    ret1y_lookback_bars: int = 1638  # kept for compatibility, but RS uses daily data

    # exits (two modes)
    # - fixed: use tp_pct/sl_pct
    # - rr_struct: use structure stop (swing low) + fixed RR to derive TP
    risk_mode: str = "fixed"  # fixed | rr_struct
    rr: float = 5/3
    sl_lookback: int = 20
    sl_atr_buffer: float = 0.0  # buffer in ATR14 units
    sl_pivot_left: int = 2
    sl_pivot_right: int = 2

    tp_pct: float = 0.13
    sl_pct: float = -0.08
    hold_max: int = 195  # ~30 trading days * 6.5 bars/day

    # deterministic warmup
    warmup_bars: int = 300


def load_1h_history(ticker: str, period: str = "730d") -> pd.DataFrame:
    """Load 1H history.

    Priority:
    1) Local Parquet store (sync recent window first)
    2) Fallback to yfinance period fetch

    Note: period kept for CLI compatibility.
    """
    try:
        from data_store import sync_and_load
        # If user requests long period (e.g. 730d), prefer yfinance direct fetch to avoid
        # silently truncating to the local store's recent window.
        if str(period).endswith('d') and int(str(period)[:-1]) > 180:
            raise RuntimeError('prefer yfinance for long period')
        # otherwise: sync recent window; keeps store fresh and accumulative
        df = sync_and_load(ticker, interval="1h", lookback_days=120)
    except Exception:
        df = yf.Ticker(ticker).history(period=period, interval="1h", auto_adjust=True)

    if df is None or df.empty:
        return pd.DataFrame()

    df = df.dropna().copy()
    # normalize index tz
    try:
        df.index = df.index.tz_convert(None)
    except Exception:
        try:
            df.index = df.index.tz_localize(None)
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


def entry_condition(df: pd.DataFrame, i: int, p: Params, rs_1y: float) -> Tuple[bool, Dict]:
    row = df.iloc[i]

    rsi = float(row.get("rsi14", 99))
    above200 = int(row.get("above_ma200", 0))
    above50 = int(row.get("above_ma50", 0))
    ret5 = float(row.get("ret_5d", 0))
    macd_h = float(row.get("macd_hist", 0))
    

    # apply dynamic ret5 downgrade (same thresholds as live scan)
    ret5_entry = p.ret5_entry
    if p.no_signal_streak >= 30:
        ret5_entry = -0.02
    elif p.no_signal_streak >= 20:
        ret5_entry = -0.025

    # RS_1Y: no longer a hard filter unless *extremely weak*
    rs_ok = (rs_1y == -999.0) or (rs_1y > p.rs_1y_floor)

    ok = (
        above200 == 1
        and rsi < p.rsi_entry
        and ret5 < ret5_entry
        and rs_ok
        and macd_h < 0
    )

    # RS_1Y score (kept consistent with signal_engine)
    rs_score = 0
    if rs_1y != -999.0:
        if rs_1y > 10:
            rs_score = 10
        elif rs_1y > 0:
            rs_score = 5
        elif rs_1y > -10:
            rs_score = 0
        else:
            rs_score = -5

    # ── risk regime flags (conservative: avoid catching falling knives) ──
    close = float(row.get("close", 0))
    ma200 = float(row.get("ma200", close))
    ma50 = float(row.get("ma50", close))
    atr14 = float(row.get("atr14", 0))
    atr_pct = (atr14 / close * 100) if close else 0.0

    # slope computed on trailing MA series up to i (no look-ahead)
    ma200_slope_pct = _ma_slope_pct(df["ma200"].iloc[: i + 1], window=50) if "ma200" in df.columns else 0.0
    ma50_crosses = _cross_count(df["close"].iloc[: i + 1], df["ma50"].iloc[: i + 1], window=80) if ("ma50" in df.columns and "close" in df.columns) else 0

    # thresholds (chosen from core-pool distribution; conservative)
    # - ret_5d <= -5% is ~5th percentile of core-pool bars → treat as knife pressure
    # - ATR% >= 3.3% is ~90th percentile → noisy/choppy regime
    ret5_pct = ret5 * 100
    knife_ret5_thresh = -5.0
    chop_atr_thresh = 3.3

    knife_risk = (
        (above200 == 0 and ma200_slope_pct < 0)
        or (ret5_pct <= knife_ret5_thresh and macd_h < 0)
        or (rs_1y != -999.0 and rs_1y <= -20.0)
    )

    chop_risk = (
        (atr_pct >= chop_atr_thresh and ma50_crosses >= 6)
        or (atr_pct >= chop_atr_thresh * 1.2)
    )

    trend_ok = (above200 == 1 and ma200_slope_pct >= 0 and (rs_1y == -999.0 or rs_1y > -10.0) and not knife_risk)

    meta = {
        "rsi14": rsi,
        "above_ma200": above200,
        "above_ma50": above50,
        "ret_5d_pct": ret5_pct,
        "ret5_entry_pct": ret5_entry * 100,
        "no_signal_streak": int(p.no_signal_streak),
        "rs_1y": rs_1y,
        "rs_1y_floor": p.rs_1y_floor,
        "rs_1y_score": rs_score,
        "macd_hist": macd_h,

        "atr_pct": round(atr_pct, 3),
        "ma200_slope_pct": round(ma200_slope_pct, 3),
        "ma50_crosses": int(ma50_crosses),

        "knife_risk": bool(knife_risk),
        "chop_risk": bool(chop_risk),
        "trend_ok": bool(trend_ok),

        "knife_ret5_thresh": knife_ret5_thresh,
        "chop_atr_thresh": chop_atr_thresh,
    }
    return ok, meta


def _ma_slope_pct(ma: pd.Series, window: int = 50) -> float:
    """Return MA slope over last `window` bars in percent (end/start - 1).

    Conservative: if not enough bars, return 0.
    """
    try:
        w = max(5, int(window))
        if ma is None or len(ma) < w + 1:
            return 0.0
        a = float(ma.iloc[-w])
        b = float(ma.iloc[-1])
        if a == 0:
            return 0.0
        return (b / a - 1.0) * 100.0
    except Exception:
        return 0.0


def _cross_count(series: pd.Series, ref: pd.Series, window: int = 50) -> int:
    """Count sign changes of (series-ref) over last `window` bars."""
    try:
        w = max(10, int(window))
        s = (series - ref).iloc[-w:].astype(float)
        # treat zeros as previous sign to avoid noisy counts
        sign = np.sign(s)
        sign = sign.replace(0, np.nan).ffill().fillna(0)
        return int((sign.shift(1) * sign < 0).sum())
    except Exception:
        return 0


def _find_pivot_lows(lows: pd.Series, left: int = 2, right: int = 2) -> pd.Series:
    """Return a boolean Series marking pivot lows.

    A pivot low at t means low[t] is strictly lower than `left` bars to the left
    and `right` bars to the right.

    Note: this is a *confirmed* pivot definition, so it needs `right` future bars.
    In backtest, using data up to entry bar i, we only consider pivots that are
    confirmable within the lookback window ending at i.
    """
    left = max(1, int(left))
    right = max(1, int(right))
    # strictly lower than both sides
    is_pivot = pd.Series(True, index=lows.index)
    for k in range(1, left + 1):
        is_pivot &= lows < lows.shift(k)
    for k in range(1, right + 1):
        is_pivot &= lows < lows.shift(-k)
    # edges cannot be pivots
    is_pivot.iloc[:left] = False
    is_pivot.iloc[-right:] = False
    return is_pivot


def _structure_sl(
    df: pd.DataFrame,
    i: int,
    lookback: int,
    atr_buffer: float,
    *,
    pivot_left: int = 2,
    pivot_right: int = 2,
) -> Optional[float]:
    """Compute structure stop loss.

    Upgrade v2 (closer to "structure" / 一买二买 semantics):
    - Prefer the most recent confirmed pivot low (fractal swing low) within lookback.
    - Fallback to min(low) if no pivot low is found.

    Optionally subtract `atr_buffer * ATR14`.
    """
    try:
        lb = max(1, int(lookback))
        start = max(0, i - lb + 1)
        window = df.iloc[start : i + 1]
        if window is None or window.empty:
            return None
        if "low" not in window.columns:
            return None

        lows = window["low"].astype(float)

        # find confirmed pivot lows *within the window*
        piv = _find_pivot_lows(lows, left=pivot_left, right=pivot_right)
        pivot_idxs = list(lows.index[piv])
        if pivot_idxs:
            # use the latest pivot low as structure SL
            last_idx = pivot_idxs[-1]
            sl = float(lows.loc[last_idx])
        else:
            sl = float(lows.min())

        if atr_buffer and "atr14" in df.columns:
            atr = float(df["atr14"].iloc[i])
            if atr > 0:
                sl = sl - float(atr_buffer) * atr
        return sl
    except Exception:
        return None


def backtest(df: pd.DataFrame, p: Params, ticker: str = "") -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    # Precompute RS_1Y once per backtest (avoid per-bar network calls)
    rs_1y = -999.0
    if compute_rs_1y_fn is not None and ticker:
        try:
            rs_1y = compute_rs_1y_fn(ticker)
        except Exception:
            rs_1y = -999.0

    trades: List[Dict] = []
    in_trade = False
    entry_i: Optional[int] = None
    entry_price: Optional[float] = None
    entry_time: Optional[pd.Timestamp] = None
    entry_meta: Dict = {}
    entry_sl: Optional[float] = None
    entry_tp: Optional[float] = None

    start_i = max(p.warmup_bars, p.ret1y_lookback_bars)  # deterministic start

    for i in range(start_i, len(df)):
        if not in_trade:
            ok, meta = entry_condition(df, i, p, rs_1y)
            if ok:
                in_trade = True
                entry_i = i
                entry_price = float(df["close"].iloc[i])
                entry_time = df.index[i]
                entry_meta = meta

                # risk model
                entry_sl = None
                entry_tp = None
                if p.risk_mode == "rr_struct":
                    sl = _structure_sl(
                        df,
                        i,
                        p.sl_lookback,
                        p.sl_atr_buffer,
                        pivot_left=p.sl_pivot_left,
                        pivot_right=p.sl_pivot_right,
                    )
                    if sl is not None and sl < entry_price:
                        entry_sl = float(sl)
                        entry_tp = float(entry_price + p.rr * (entry_price - entry_sl))
                # fallback: fixed % stop/target
                if entry_sl is None:
                    entry_sl = float(entry_price * (1.0 + p.sl_pct))
                    entry_tp = float(entry_price * (1.0 + p.tp_pct))

                entry_meta = {
                    **entry_meta,
                    "risk_mode": p.risk_mode,
                    "rr": float(p.rr),
                    "sl_lookback": int(p.sl_lookback),
                    "sl_atr_buffer": float(p.sl_atr_buffer),
                    "entry_sl": round(entry_sl, 4),
                    "entry_tp": round(entry_tp, 4),
                }
        else:
            assert entry_i is not None and entry_price is not None and entry_time is not None
            bars_held = i - entry_i
            cur = float(df["close"].iloc[i])
            cur_ret = (cur - entry_price) / entry_price

            reason = None
            if entry_tp is not None and cur >= entry_tp:
                reason = "TP"
            elif entry_sl is not None and cur <= entry_sl:
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
                entry_sl = None
                entry_tp = None

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

    ap.add_argument("--tp", type=float, default=0.13, help="Fixed TP pct (used when --risk_mode=fixed)")
    ap.add_argument("--sl", type=float, default=-0.08, help="Fixed SL pct (used when --risk_mode=fixed)")
    ap.add_argument("--hold", type=int, default=195)

    ap.add_argument("--risk_mode", type=str, default="fixed", choices=["fixed", "rr_struct"], help="Exit model")
    ap.add_argument("--rr", type=float, default=5/3, help="Risk-reward for rr_struct mode (TP = entry + rr*(entry-SL))")
    ap.add_argument("--sl_lookback", type=int, default=30, help="Structure SL lookback bars for rr_struct")
    ap.add_argument("--sl_atr_buffer", type=float, default=0.5, help="Subtract buffer*ATR14 from structure SL (default 0.5)")
    ap.add_argument("--sl_pivot_left", type=int, default=2, help="Pivot-low (fractal) left bars")
    ap.add_argument("--sl_pivot_right", type=int, default=2, help="Pivot-low (fractal) right bars")

    ap.add_argument("--rsi", type=float, default=45)
    ap.add_argument("--ret5", type=float, default=-0.03)
    ap.add_argument("--rs_1y_floor", type=float, default=-10.0, help="RS_1Y floor filter (vs SPY). Only blocks extremely weak names; default -10.0")
    ap.add_argument("--no_signal", type=int, default=0, help="Market no-signal streak (scans). Used to auto-downgrade ret5: 0->-3%%, >=20->-2.5%%, >=30->-2%%")

    ap.add_argument("--warmup", type=int, default=300)
    ap.add_argument("--ret1y_lookback", type=int, default=1638)

    args = ap.parse_args()

    p = Params(
        rsi_entry=args.rsi,
        ret5_entry=args.ret5,
        no_signal_streak=args.no_signal,
        rs_1y_floor=args.rs_1y_floor,
        risk_mode=args.risk_mode,
        rr=args.rr,
        sl_lookback=args.sl_lookback,
        sl_atr_buffer=args.sl_atr_buffer,
        sl_pivot_left=args.sl_pivot_left,
        sl_pivot_right=args.sl_pivot_right,

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

    trades = backtest(df, p, ticker=args.ticker)
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
