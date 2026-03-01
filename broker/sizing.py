"""Position sizing and risk controls.

We size by risk per trade using stop loss distance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class SizingConfig:
    risk_pct_equity: float = 0.003  # 0.3% of equity per trade
    max_position_pct_equity: float = 0.08
    min_notional: float = 300.0
    max_notional: float = 6000.0

    min_sl_pct: float = 0.03
    max_sl_pct: float = 0.15


def compute_qty(equity: float, entry: float, sl: float, cfg: Optional[SizingConfig] = None) -> int:
    cfg = cfg or SizingConfig()
    if equity <= 0 or entry <= 0 or sl <= 0:
        return 0

    risk_per_share = entry - sl
    if risk_per_share <= 0:
        return 0

    sl_pct = risk_per_share / entry
    if sl_pct < cfg.min_sl_pct or sl_pct > cfg.max_sl_pct:
        return 0

    risk_budget = equity * cfg.risk_pct_equity
    qty = int(risk_budget / risk_per_share)

    notional = qty * entry
    if notional < cfg.min_notional:
        qty = int(cfg.min_notional / entry)
    if qty <= 0:
        return 0

    notional = qty * entry
    if notional > cfg.max_notional:
        qty = int(cfg.max_notional / entry)

    return max(0, qty)


def marketable_limit_price(side: str, bid: float | None, ask: float | None, last: float | None) -> float | None:
    """Aggressive limit price to improve fill probability (staleness-safe).

    BUY: prefer ask, else last*1.002
    SELL: prefer bid, else last*0.998
    """
    s = (side or '').lower()
    if s in ('buy', 'b'):
        if ask:
            return float(ask)
        if last:
            return float(last) * 1.002
    if s in ('sell', 's'):
        if bid:
            return float(bid)
        if last:
            return float(last) * 0.998
    return None
