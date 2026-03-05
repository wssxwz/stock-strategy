"""Replay backtest to quantify *dedupe logic* impact (old vs new).

Why
- The recent changes (#2/#3/#4) mainly affect messaging + execution gating.
- Classic bar-by-bar backtests do not capture dedupe/upgrade/rate-limit.

This script replays an hourly scan over a ticker universe, then applies:
- Old dedupe: (ticker, date, score_bucket//10)
- New dedupe: (ticker, date, exec_mode) + upgrade resend rules

Then it simulates a simple capital-constrained executor:
- max_open_pos = 1 (serial trades)
- max_new_buys_per_day = 1
- choose Top1 by score among *eligible new* signals each scan

Trade model (approx)
- entry at bar close of the scan bar
- exit: fixed TP/SL or max holding bars

This is NOT a perfect replica of LongPort execution/slippage.
It is intended to quantify whether the new dedupe creates *incremental trades*
(or earlier entries) and how that changes PnL distribution.

Usage
  ./venv/bin/python jobs/replay_dedupe_backtest.py --scope full --period 180d
  ./venv/bin/python jobs/replay_dedupe_backtest.py --scope full --period 365d --out reports/dedupe_report_365d.md
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "monitor"))
sys.path.insert(0, os.path.join(ROOT, "src"))

from config import WATCHLIST, WATCHLIST_FULL, NOTIFY
from signal_engine import score_signal, _structure_signals

try:
    from data_store import sync_and_load
except Exception:
    sync_and_load = None

from analyzer.indicators import add_all_indicators


def _score_bucket(score: float) -> int:
    try:
        s = float(score or 0)
    except Exception:
        s = 0.0
    return int(s // 10 * 10)


def old_key(ticker: str, dt: pd.Timestamp, score: float) -> str:
    d = dt.strftime("%Y-%m-%d")
    return f"{ticker}_{d}_{_score_bucket(score)}"


def new_key(ticker: str, dt: pd.Timestamp, exec_mode: str) -> str:
    d = dt.strftime("%Y-%m-%d")
    mode = (exec_mode or "UNKNOWN").upper()
    return f"{ticker}_{d}_{mode}"


def should_send_again(
    score: float,
    exec_mode: str,
    prev: Optional[dict],
    cur_ts: pd.Timestamp,
    *,
    upgrade_min_delta: float,
    upgrade_min_interval_min: int,
    upgrade_strong_score: float,
) -> Tuple[bool, str]:
    if not prev:
        return True, "first"

    # rate limit
    try:
        last_iso = prev.get("time")
        if last_iso:
            last_dt = datetime.fromisoformat(last_iso)
            if (cur_ts.to_pydatetime() - last_dt).total_seconds() < upgrade_min_interval_min * 60:
                return False, f"rate_limited<{upgrade_min_interval_min}m"
    except Exception:
        pass

    prev_mode = (prev.get("exec_mode") or "").upper()
    cur_mode = (exec_mode or "").upper()
    if prev_mode and cur_mode and prev_mode != cur_mode:
        return True, f"mode:{prev_mode}->{cur_mode}"

    prev_score = float(prev.get("score", 0) or 0)
    cur_score = float(score or 0)

    if _score_bucket(cur_score) > _score_bucket(prev_score):
        return True, f"bucket:{_score_bucket(prev_score)}->{_score_bucket(cur_score)}"

    if (cur_score - prev_score) >= upgrade_min_delta:
        return True, f"delta:+{cur_score - prev_score:.1f}>={upgrade_min_delta}"

    if cur_score >= upgrade_strong_score:
        return True, "strong"

    return False, "no_change"


def load_1h_history(ticker: str, period: str) -> pd.DataFrame:
    if sync_and_load is None:
        raise RuntimeError("sync_and_load unavailable; run inside repo venv")

    lb = 120
    if str(period).endswith("d"):
        try:
            days = int(str(period)[:-1])
            lb = min(800, max(120, days + 20))
        except Exception:
            pass

    df = sync_and_load(
        ticker,
        interval="1h",
        lookback_days=lb,
        max_auto_lookback_days=800,
    )
    # trim to requested period window (sync_and_load may return a longer cached range)
    if str(period).endswith('d') and df is not None and not df.empty:
        try:
            days = int(str(period)[:-1])
            end_ts = df.index[-1]
            start_ts = end_ts - pd.Timedelta(days=days + 2)
            df = df[df.index >= start_ts]
        except Exception:
            pass

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

    # harmonize
    if "bb_pct" not in df.columns and "bb_pct20" in df.columns:
        df["bb_pct"] = df["bb_pct20"]
    if "atr_pct14" not in df.columns and ("atr14" in df.columns and "close" in df.columns):
        df["atr_pct14"] = (df["atr14"] / df["close"]) * 100.0

    return df


def route_exec_mode(df: pd.DataFrame, i: int, ticker: str, *, use_structure: bool = False) -> Tuple[str, dict]:
    """Approx routing logic.

    NOTE:
    - Structure pattern detection is expensive in full-universe replay.
    - By default we disable STRUCT and only model MR via BB% gate.
    """
    row = df.iloc[i]

    bb = float(row.get("bb_pct", 0.5) or 0.5)
    rsi = float(row.get("rsi14", 50) or 50)
    above200 = bool(row.get("above_ma200", 0))

    atr_pct14 = row.get("atr_pct14", None)
    atr_ok = False
    try:
        atr_ok = (atr_pct14 is not None) and (float(atr_pct14) <= 3.5)
    except Exception:
        atr_ok = False

    st = {"enabled": False, "signals": [], "best": None}
    if use_structure:
        try:
            start = max(0, i - 260)
            st = _structure_signals(df.iloc[start : i + 1], ticker)
        except Exception:
            st = {"enabled": False, "signals": [], "best": None}

    st_signals = st.get("signals") or []
    st_best = st.get("best") or None

    if use_structure and st_signals and st_best and above200 and atr_ok:
        return "STRUCT", {"structure": st, "route_reason": f"STRUCT({st_best.get('type')})"}
    if bb < 0.35:
        return "MR", {"structure": st, "route_reason": "MR bb<0.35" + (" rsi<25" if rsi < 25 else "")}
    return "SKIP", {"structure": st, "route_reason": "skip"}


@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    ticker: str
    entry: float
    exit: float
    ret: float
    exit_reason: str


def simulate(
    universe: List[str],
    period: str,
    *,
    tp_pct: float,
    sl_pct: float,
    hold_max: int,
    min_score: float,
    max_new_buys_per_day: int,
    mode: str,
    upgrade_min_delta: float,
    upgrade_min_interval_min: int,
    upgrade_strong_score: float,
    use_structure: bool = False,
) -> dict:
    data: Dict[str, pd.DataFrame] = {}
    total = len(universe)
    for n, t in enumerate(universe, 1):
        if n % 25 == 0 or n == 1 or n == total:
            print(f"[load] {n}/{total} {t}")
        try:
            df = load_1h_history(t, period)
            if df is None or df.empty:
                continue
            data[t] = df
        except Exception:
            continue

    if not data:
        return {"trades": [], "equity": 1.0, "notes": "no data"}

    all_idx = sorted(set().union(*[set(df.index) for df in data.values()]))

    sent: Dict[str, dict] = {}
    trades: List[Trade] = []

    in_pos = False
    pos_ticker = None
    entry_i = None
    entry_price = None
    entry_time = None

    day_buy_count: Dict[str, int] = {}

    for ts in all_idx:
        day = ts.strftime("%Y-%m-%d")

        # manage open position
        if in_pos and pos_ticker in data:
            dfp = data[pos_ticker]
            if ts in dfp.index:
                i = int(dfp.index.get_loc(ts))
                price = float(dfp["close"].iloc[i])
                if entry_i is not None and entry_price is not None and entry_time is not None:
                    if (price - entry_price) / entry_price >= tp_pct:
                        trades.append(Trade(entry_time, ts, pos_ticker, entry_price, price, (price - entry_price) / entry_price, "TP"))
                        in_pos = False
                    elif (price - entry_price) / entry_price <= sl_pct:
                        trades.append(Trade(entry_time, ts, pos_ticker, entry_price, price, (price - entry_price) / entry_price, "SL"))
                        in_pos = False
                    elif (i - entry_i) >= hold_max:
                        trades.append(Trade(entry_time, ts, pos_ticker, entry_price, price, (price - entry_price) / entry_price, "HOLD_MAX"))
                        in_pos = False

                if not in_pos:
                    pos_ticker = None
                    entry_i = None
                    entry_price = None
                    entry_time = None

        if in_pos:
            continue

        # per-day entry constraint
        if day_buy_count.get(day, 0) >= max_new_buys_per_day:
            continue

        candidates = []
        for t, df in data.items():
            if ts not in df.index:
                continue
            i = int(df.index.get_loc(ts))
            if i < 300:
                continue

            row = df.iloc[i]
            sig = score_signal(row, t)
            score = float(sig.get("score", 0) or 0)
            if score < min_score:
                continue

            exec_mode, _extra = route_exec_mode(df, i, t, use_structure=use_structure)
            if exec_mode == "SKIP":
                continue

            if mode == "old":
                k = old_key(t, ts, score)
                ok = k not in sent
                reason = "old:first" if ok else "old:dup"
            else:
                k = new_key(t, ts, exec_mode)
                prev = sent.get(k)
                ok, reason = should_send_again(
                    score,
                    exec_mode,
                    prev,
                    ts,
                    upgrade_min_delta=upgrade_min_delta,
                    upgrade_min_interval_min=upgrade_min_interval_min,
                    upgrade_strong_score=upgrade_strong_score,
                )

            if not ok:
                continue

            price = float(row.get("close", np.nan))
            if np.isnan(price):
                continue

            candidates.append({"ticker": t, "score": score, "exec_mode": exec_mode, "price": price, "idx": i, "time": ts, "reason": reason})

        if not candidates:
            continue

        best = sorted(candidates, key=lambda x: (x["score"], x["exec_mode"] == "STRUCT"), reverse=True)[0]

        if mode == "old":
            k = old_key(best["ticker"], best["time"], best["score"])
        else:
            k = new_key(best["ticker"], best["time"], best["exec_mode"])

        sent[k] = {
            "ticker": best["ticker"],
            "score": best["score"],
            "exec_mode": best["exec_mode"],
            "time": best["time"].to_pydatetime().isoformat(),
            "reason": best["reason"],
        }

        in_pos = True
        pos_ticker = best["ticker"]
        entry_i = best["idx"]
        entry_price = float(best["price"])
        entry_time = best["time"]
        day_buy_count[day] = day_buy_count.get(day, 0) + 1

    if in_pos and pos_ticker and pos_ticker in data and entry_time is not None and entry_price is not None:
        dfp = data[pos_ticker]
        last_ts = dfp.index[-1]
        price = float(dfp["close"].iloc[-1])
        trades.append(Trade(entry_time, last_ts, pos_ticker, entry_price, price, (price - entry_price) / entry_price, "EOD"))

    eq = 1.0
    for tr in trades:
        eq *= (1.0 + tr.ret)

    win = sum(1 for tr in trades if tr.ret > 0)
    return {
        "trades": trades,
        "equity": eq,
        "trade_count": len(trades),
        "win": win,
        "loss": len(trades) - win,
        "win_rate": (win / len(trades)) if trades else 0.0,
    }


def summarize(trades: List[Trade]) -> dict:
    if not trades:
        return {"count": 0}
    rets = np.array([t.ret for t in trades], dtype=float)
    return {
        "count": len(trades),
        "avg": float(np.mean(rets)),
        "med": float(np.median(rets)),
        "p10": float(np.percentile(rets, 10)),
        "p90": float(np.percentile(rets, 90)),
        "min": float(np.min(rets)),
        "max": float(np.max(rets)),
    }


def format_report(title: str, old: dict, new: dict) -> str:
    old_eq = float(old.get("equity", 1.0) or 1.0)
    new_eq = float(new.get("equity", 1.0) or 1.0)
    delta = (new_eq / old_eq - 1.0) if old_eq else 0.0

    so = summarize(old.get("trades") or [])
    sn = summarize(new.get("trades") or [])

    lines = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append("## Headline")
    lines.append(f"- Old equity: **{old_eq:.4f}**")
    lines.append(f"- New equity: **{new_eq:.4f}**")
    lines.append(f"- Delta (new vs old): **{delta*100:.2f}%**")
    lines.append("")
    lines.append("## Trades")
    lines.append(f"- Old trades: {old.get('trade_count',0)} | win_rate={old.get('win_rate',0)*100:.1f}%")
    lines.append(f"- New trades: {new.get('trade_count',0)} | win_rate={new.get('win_rate',0)*100:.1f}%")
    lines.append("")
    lines.append("## Return distribution (per-trade)")

    def fmt(s):
        if not s or s.get("count", 0) == 0:
            return "(no trades)"
        return (
            f"count={s['count']} avg={s['avg']*100:.2f}% med={s['med']*100:.2f}% "
            f"p10={s['p10']*100:.2f}% p90={s['p90']*100:.2f}% min={s['min']*100:.2f}% max={s['max']*100:.2f}%"
        )

    lines.append(f"- Old: {fmt(so)}")
    lines.append(f"- New: {fmt(sn)}")
    lines.append("")

    old_tr = old.get("trades") or []
    new_tr = new.get("trades") or []

    old_set = {(t.entry_time, t.ticker) for t in old_tr}
    new_only = [t for t in new_tr if (t.entry_time, t.ticker) not in old_set]

    if new_only:
        lines.append("## New-only trades (first 10)")
        for t in new_only[:10]:
            lines.append(f"- {t.entry_time} {t.ticker}: {t.ret*100:.2f}% ({t.exit_reason})")
        lines.append("")

    return "\n".join(lines)


def load_core_and_held() -> Tuple[List[str], List[str]]:
    core = []
    held = []
    try:
        import json

        obj = json.loads(open(os.path.join(ROOT, "core_holdings.json"), "r", encoding="utf-8").read())
        core = sorted(list((obj.get("tickers") or {}).keys()))
    except Exception:
        core = []

    try:
        import json

        obj = json.loads(open(os.path.join(ROOT, "monitor", "portfolio.json"), "r", encoding="utf-8").read())
        held = sorted(list(obj.keys()))
    except Exception:
        held = []

    return core, held


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", choices=["tier", "full"], default="full")
    ap.add_argument("--period", default="180d")
    ap.add_argument("--out", default="")
    ap.add_argument("--use-structure", action="store_true", help="Enable STRUCT routing (slow).")

    ap.add_argument("--tp", type=float, default=0.13)
    ap.add_argument("--sl", type=float, default=-0.08)
    ap.add_argument("--hold", type=int, default=195)
    ap.add_argument("--min-score", type=float, default=float(NOTIFY.get("min_score", 70)))

    ap.add_argument("--max-new-buys-per-day", type=int, default=1)

    ap.add_argument("--upgrade-min-delta", type=float, default=float(os.environ.get("UPGRADE_MIN_DELTA", "5")))
    ap.add_argument("--upgrade-min-interval-min", type=int, default=int(os.environ.get("UPGRADE_MIN_INTERVAL_MIN", "120")))
    ap.add_argument("--upgrade-strong-score", type=float, default=float(os.environ.get("UPGRADE_STRONG_SCORE", "85")))

    args = ap.parse_args()

    universe = WATCHLIST_FULL if args.scope == "full" else WATCHLIST

    old = simulate(
        universe,
        args.period,
        tp_pct=args.tp,
        sl_pct=args.sl,
        hold_max=args.hold,
        min_score=args.min_score,
        max_new_buys_per_day=args.max_new_buys_per_day,
        mode="old",
        upgrade_min_delta=args.upgrade_min_delta,
        upgrade_min_interval_min=args.upgrade_min_interval_min,
        upgrade_strong_score=args.upgrade_strong_score,
        use_structure=args.use_structure,
    )

    new = simulate(
        universe,
        args.period,
        tp_pct=args.tp,
        sl_pct=args.sl,
        hold_max=args.hold,
        min_score=args.min_score,
        max_new_buys_per_day=args.max_new_buys_per_day,
        mode="new",
        upgrade_min_delta=args.upgrade_min_delta,
        upgrade_min_interval_min=args.upgrade_min_interval_min,
        upgrade_strong_score=args.upgrade_strong_score,
        use_structure=args.use_structure,
    )

    core, held = load_core_and_held()
    coreheld = sorted(list(set(core + held)))

    old_ch = simulate(
        coreheld,
        args.period,
        tp_pct=args.tp,
        sl_pct=args.sl,
        hold_max=args.hold,
        min_score=args.min_score,
        max_new_buys_per_day=args.max_new_buys_per_day,
        mode="old",
        upgrade_min_delta=args.upgrade_min_delta,
        upgrade_min_interval_min=args.upgrade_min_interval_min,
        upgrade_strong_score=args.upgrade_strong_score,
        use_structure=args.use_structure,
    )

    new_ch = simulate(
        coreheld,
        args.period,
        tp_pct=args.tp,
        sl_pct=args.sl,
        hold_max=args.hold,
        min_score=args.min_score,
        max_new_buys_per_day=args.max_new_buys_per_day,
        mode="new",
        upgrade_min_delta=args.upgrade_min_delta,
        upgrade_min_interval_min=args.upgrade_min_interval_min,
        upgrade_strong_score=args.upgrade_strong_score,
        use_structure=args.use_structure,
    )

    text = []
    text.append(format_report(f"Dedupe impact replay ({args.scope} universe, period={args.period})", old, new))
    text.append("\n---\n")
    text.append(format_report(f"Core + Held (period={args.period})", old_ch, new_ch))
    out = "\n".join(text)

    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"WROTE:{args.out}")
    else:
        print(out)


if __name__ == "__main__":
    main()
