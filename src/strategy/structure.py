"""Structure-based entry logic (60m) — breakout + pullback confirmation.

This module is the foundation for "操盘手" style trading:
- Plan the trade: identify structure, wait for confirmation, define invalidation (SL).
- Not mean-reversion by RSI alone.

We implement a pragmatic, codeable approximation of:
- 1-buy (trend start): breakout + pullback hold + reclaim
- 2-buy (trend continuation): pullback to key zone (breakout level / MA50) + confirm

All computations must avoid look-ahead (no future bars).

Outputs are *signals* with:
- entry_price (current close)
- structure_sl (invalidation level)
- tp derived by RR (e.g., 5/3)

NOTE: This is intentionally conservative ("不接飞刀").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd


@dataclass
class StructureParams:
    # Structure window
    box_lookback: int = 80  # ~3 trading days of 1H bars (6.5*3≈20) but we use bigger for robustness

    # Breakout validation
    breakout_buffer_atr: float = 0.2  # breakout must clear box_high by this * ATR14
    min_breakout_bars_ago: int = 2    # breakout must have occurred at least N bars ago (avoid same-bar noise)

    # Pullback/hold
    pullback_max_bars: int = 30
    hold_buffer_atr: float = 0.3  # how much it can pierce level and still be "hold"

    # Confirmation
    confirm_close_buffer_atr: float = 0.1  # close back above level by buffer*ATR

    # Trend filters (conservative)
    require_above_ma200: bool = True
    require_ma200_slope_nonneg: bool = True

    # Risk
    rr: float = 5 / 3


def _ma_slope_pct(ma: pd.Series, window: int = 50) -> float:
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


def _atr(row: pd.Series) -> float:
    try:
        a = float(row.get("atr14", 0.0))
        return a if a > 0 else 0.0
    except Exception:
        return 0.0


def compute_box(df: pd.DataFrame, end_i: int, lookback: int) -> Optional[Tuple[float, float]]:
    """Return (box_high, box_low) from the last `lookback` bars ending at end_i (inclusive)."""
    if df is None or df.empty:
        return None
    lb = max(20, int(lookback))
    start = max(0, end_i - lb + 1)
    w = df.iloc[start : end_i + 1]
    if w.empty or "high" not in w.columns or "low" not in w.columns:
        return None
    return float(w["high"].max()), float(w["low"].min())


def structure_1buy_signal(df: pd.DataFrame, i: int, p: StructureParams) -> Optional[Dict]:
    """1-buy: breakout + pullback hold + reclaim.

    Implementation (no look-ahead):
    - Define a prior box using bars [i-lookback-pullback_max_bars, i-pullback_max_bars]
      so that breakout/pullback can occur after the box.
    - Detect breakout above box_high.
    - Within the last `pullback_max_bars`, price pulled back to near box_high and held.
    - Current close reclaims above box_high (confirmation).
    """
    if i < p.box_lookback + p.pullback_max_bars + 5:
        return None

    row = df.iloc[i]
    close = float(row.get("close", 0))
    if close <= 0:
        return None

    if p.require_above_ma200 and int(row.get("above_ma200", 0)) != 1:
        return None

    if p.require_ma200_slope_nonneg and "ma200" in df.columns:
        slope = _ma_slope_pct(df["ma200"].iloc[: i + 1], window=50)
        if slope < 0:
            return None

    atr = _atr(row)

    # build a "prior box" window that ends before the pullback window
    box_end = i - p.pullback_max_bars
    box = compute_box(df, box_end, p.box_lookback)
    if box is None:
        return None
    box_high, box_low = box

    breakout_level = box_high
    breakout_req = breakout_level + p.breakout_buffer_atr * atr

    # detect breakout occurrence in the interval after box_end
    post = df.iloc[box_end + 1 : i + 1]
    if post.empty:
        return None

    # breakout bar index (relative)
    breakout_mask = post["close"] > breakout_req
    if not bool(breakout_mask.any()):
        return None

    breakout_pos = int(np.argmax(breakout_mask.values))
    breakout_i = (box_end + 1) + breakout_pos

    if i - breakout_i < p.min_breakout_bars_ago:
        return None

    # pullback window from breakout_i to i
    pb = df.iloc[breakout_i : i + 1]
    if pb.empty:
        return None

    # must have pulled back near the breakout level and held
    hold_floor = breakout_level - p.hold_buffer_atr * atr
    pulled_back = float(pb["low"].min()) <= breakout_level
    held = float(pb["low"].min()) >= hold_floor

    if not (pulled_back and held):
        return None

    # confirmation: current close back above level
    confirm_req = breakout_level + p.confirm_close_buffer_atr * atr
    if close <= confirm_req:
        return None

    # structure SL: invalidation = pullback swing low (conservative) - buffer
    sl = float(pb["low"].min()) - 0.1 * atr
    if sl >= close:
        return None

    tp = close + p.rr * (close - sl)

    return {
        "type": "1buy",
        "box_high": breakout_level,
        "box_low": box_low,
        "breakout_i": int(breakout_i),
        "entry": close,
        "sl": sl,
        "tp": tp,
        "rr": float(p.rr),
    }


def structure_2buy_signal(df: pd.DataFrame, i: int, p: StructureParams) -> Optional[Dict]:
    """2-buy: trend established, pullback to key zone (breakout level / MA50) + confirm.

    Pragmatic definition:
    - Use a prior box like 1buy.
    - Require that a breakout happened sufficiently earlier.
    - After breakout, price makes a pullback that tags near either:
        (a) breakout_level (box_high), or
        (b) MA50 zone
      and then closes back above MA50 (or above breakout_level).
    """
    if i < p.box_lookback + p.pullback_max_bars + 5:
        return None

    row = df.iloc[i]
    close = float(row.get("close", 0))
    if close <= 0:
        return None

    if p.require_above_ma200 and int(row.get("above_ma200", 0)) != 1:
        return None

    if p.require_ma200_slope_nonneg and "ma200" in df.columns:
        slope = _ma_slope_pct(df["ma200"].iloc[: i + 1], window=50)
        if slope < 0:
            return None

    atr = _atr(row)

    box_end = i - p.pullback_max_bars
    box = compute_box(df, box_end, p.box_lookback)
    if box is None:
        return None
    box_high, box_low = box

    breakout_level = box_high
    breakout_req = breakout_level + p.breakout_buffer_atr * atr

    post = df.iloc[box_end + 1 : i + 1]
    if post.empty:
        return None

    breakout_mask = post["close"] > breakout_req
    if not bool(breakout_mask.any()):
        return None

    breakout_pos = int(np.argmax(breakout_mask.values))
    breakout_i = (box_end + 1) + breakout_pos

    # ensure we are not on immediate breakout (needs a pullback)
    if i - breakout_i < 6:
        return None

    pb = df.iloc[breakout_i : i + 1]
    if pb.empty:
        return None

    ma50 = float(row.get("ma50", close))

    zone_level = max(breakout_level, ma50)
    zone_floor = zone_level - p.hold_buffer_atr * atr

    tagged = float(pb["low"].min()) <= zone_level
    held = float(pb["low"].min()) >= zone_floor
    if not (tagged and held):
        return None

    # confirm reclaim above MA50 and/or breakout_level
    confirm_level = max(ma50, breakout_level)
    confirm_req = confirm_level + p.confirm_close_buffer_atr * atr
    if close <= confirm_req:
        return None

    sl = float(pb["low"].min()) - 0.1 * atr
    if sl >= close:
        return None

    tp = close + p.rr * (close - sl)

    return {
        "type": "2buy",
        "box_high": breakout_level,
        "box_low": box_low,
        "breakout_i": int(breakout_i),
        "entry": close,
        "sl": sl,
        "tp": tp,
        "rr": float(p.rr),
        "zone_level": zone_level,
    }
