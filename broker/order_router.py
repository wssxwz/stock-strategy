"""Convert strategy signals to paper-trading OrderIntent.

This module is intentionally conservative:
- Only supports US stocks (SYMBOL.US)
- Uses marketable limit prices (ask/bid) to reduce stale-price risk
- Sizes using stop-loss distance and a risk budget

No real order submission here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from broker.symbol_map import to_longport_symbol
from broker.sizing import compute_qty, marketable_limit_price, SizingConfig
from broker.paper_executor import OrderIntent, make_intent


@dataclass
class PaperTradeConfig:
    equity: float = 100000.0
    sizing: SizingConfig = SizingConfig()

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

    # qty by risk
    qty = compute_qty(cfg.equity, entry=limit_px, sl=sl, cfg=cfg.sizing)
    if qty <= 0:
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
