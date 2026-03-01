"""Build exit (sell) intents from portfolio alerts + live positions.

We prioritize stop-loss exits.
"""

from __future__ import annotations

from typing import Optional

from broker.paper_executor import OrderIntent, make_intent
from broker.sizing import marketable_limit_price


def build_exit_intent(
    symbol: str,
    qty: int,
    quote: dict,
    *,
    reason: str,
) -> Optional[OrderIntent]:
    if not symbol or qty <= 0:
        return None
    bid = quote.get('bid')
    ask = quote.get('ask')
    last = quote.get('last')
    limit_px = marketable_limit_price('sell', bid=bid, ask=ask, last=last)
    if limit_px is None and last:
        limit_px = float(last) * 0.998
    if limit_px is None:
        return None

    return make_intent(
        symbol=symbol,
        side='Sell',
        qty=int(qty),
        order_type='LO',
        limit_price=round(float(limit_px), 2),
        sl_price=None,
        tp_price=None,
        remark=f"exit|{reason}"[:64],
        source={'reason': reason},
    )
