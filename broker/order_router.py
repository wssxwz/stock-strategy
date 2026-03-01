"""Convert strategy signals to paper-trading OrderIntent.

This module is intentionally conservative:
- Only supports US stocks (SYMBOL.US)
- Uses marketable limit prices (ask/bid) to reduce stale-price risk
- Sizes using stop-loss distance and a risk budget

No real order submission here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

from broker.symbol_map import to_longport_symbol
from broker.sizing import compute_qty, marketable_limit_price, SizingConfig
from broker.paper_executor import OrderIntent, make_intent


@dataclass
class PaperTradeConfig:
    # equity in USD (we size US trading by USD available cash)
    equity: float = 100000.0
    sizing: SizingConfig = field(default_factory=SizingConfig)

    max_sl_pct: float = 0.10
    max_position_pct: float = 0.08

    min_price_usd: float = 5.0

    # only place paper orders for these exec modes
    allow_exec_modes: Tuple[str, ...] = ("STRUCT", "MR")


def build_order_intent(
    sig: dict,
    quote: dict,
    cfg: Optional[PaperTradeConfig] = None,
) -> Optional[OrderIntent]:
    """Build a paper OrderIntent from a strategy signal.

    quote: {last,bid,ask}
    """
    cfg = cfg or PaperTradeConfig()

    exec_mode = (sig.get('exec_mode') or '').upper()
    if exec_mode not in cfg.allow_exec_modes:
        return None

    # MR trend filter (avoid catching falling knives): require above_ma50 OR ma50 slope >= 0
    if exec_mode == 'MR':
        try:
            above_ma50 = bool(sig.get('above_ma50', False))
            ma50_slope = float(sig.get('ma50_slope', 0) or 0)
        except Exception:
            above_ma50 = False
            ma50_slope = 0.0
        if not (above_ma50 or ma50_slope >= 0):
            return None

    ticker = sig.get('ticker')
    if not ticker:
        return None

    symbol = to_longport_symbol(ticker)

    # side: buy for now (sell handled by EXIT_SIGNAL elsewhere)
    side = 'Buy'

    entry_ref = sig.get('price') or sig.get('bar_close')
    sl = sig.get('sl_price')
    tp = sig.get('tp_price')

    try:
        entry_ref = float(entry_ref)
        sl = float(sl)
        tp = float(tp)
    except Exception:
        return None

    # quote fields
    last = quote.get('last')
    bid = quote.get('bid')
    ask = quote.get('ask')

    limit_px = marketable_limit_price('buy', bid=bid, ask=ask, last=last)
    if limit_px is None:
        # fallback: small premium over entry_ref
        limit_px = entry_ref * 1.002


    # Below min price filter (avoid penny/low-quality names)
    try:
        px_check = float(last or limit_px or 0)
        if px_check > 0 and px_check < cfg.min_price_usd:
            return None
    except Exception:
        pass

    # qty by risk
    qty = compute_qty(cfg.equity, entry=limit_px, sl=sl, cfg=cfg.sizing)

    # Hard guard: do not allow too-wide SL for small accounts
    sl_pct = (limit_px - sl) / limit_px if limit_px else 1.0
    if sl_pct > cfg.max_sl_pct:
        return None

    # Allow min 1-share start (user choice B)
    if qty <= 0:
        qty = 1  # min qty fallback

    # Per-symbol notional cap (with a minimum floor so small accounts can start with 1 share)
    cap_notional = max(cfg.equity * cfg.max_position_pct, cfg.sizing.min_notional)
    if (qty * limit_px) > cap_notional:
        return None

    # Absolute notional cap
    if (qty * limit_px) > cfg.sizing.max_notional:
        return None

    remark = (
        f"paper|{exec_mode}|score={sig.get('score')}|"
        f"reason={sig.get('exec_reason','')}|"
        f"bar={sig.get('bar_time','')}"
    )

    return make_intent(
        symbol=symbol,
        side=side,
        qty=int(qty),
        order_type='LO',
        limit_price=round(float(limit_px), 2),
        sl_price=round(float(sl), 2),
        tp_price=round(float(tp), 2),
        remark=remark,
        source={
            'ticker': ticker,
            'exec_mode': exec_mode,
            'exec_reason': sig.get('exec_reason'),
            'score': sig.get('score'),
            'price_source': sig.get('price_source'),
            'scan_time': sig.get('scan_time'),
        },
    )
