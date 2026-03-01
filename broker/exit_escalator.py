"""Exit escalation logic for STOP_LOSS sells.

When STOP_LOSS is triggered but a sell order is still pending (or failed),
we escalate by cancelling/replacing with a more aggressive marketable limit.

Hard-gated by live trading flags; dry-run returns synthetic order ids.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List

from broker.live_executor import submit_live_order
from broker.paper_executor import OrderIntent
from broker.sizing import marketable_limit_price
from broker.longport_client import load_config, make_trade_ctx, make_quote_ctx, get_quote


@dataclass
class EscalationConfig:
    discounts: List[float] = None  # e.g. [0.998, 0.995, 0.990]
    max_attempts: int = 3

    def __post_init__(self):
        if self.discounts is None:
            self.discounts = [0.998, 0.995, 0.990]


def _build_more_aggressive_sell_intent(symbol: str, qty: int, *, attempt: int, quote_last: float | None, bid: float | None, ask: float | None) -> Optional[OrderIntent]:
    if qty <= 0:
        return None
    # base marketable limit
    base = marketable_limit_price('sell', bid=bid, ask=ask, last=quote_last)
    if base is None and quote_last:
        base = float(quote_last) * 0.998
    if base is None:
        return None

    # apply extra aggressiveness by multiplying last (or base)
    # attempt 0 -> 0.998, attempt 1 -> 0.995 ...
    disc_seq = [0.998, 0.995, 0.990, 0.985]
    disc = disc_seq[min(max(attempt, 0), len(disc_seq) - 1)]

    px = base
    if quote_last:
        px = float(quote_last) * disc

    from broker.paper_executor import make_intent
    return make_intent(
        symbol=symbol,
        side='Sell',
        qty=int(qty),
        order_type='LO',
        limit_price=round(float(px), 2),
        sl_price=None,
        tp_price=None,
        remark=f"exit_escalate|STOP_LOSS|a{attempt}"[:64],
        source={'reason': 'STOP_LOSS', 'attempt': attempt},
    )


def cancel_order(order_id: str) -> bool:
    cfg = load_config()
    tctx = make_trade_ctx(cfg)
    try:
        tctx.cancel_order(order_id)
        return True
    except Exception:
        return False


def escalate_stop_loss_sell(symbol: str, qty: int, *, attempt: int, dry_run: bool = True) -> tuple[bool, str, Optional[str]]:
    """Return (ok, msg, new_order_id)."""
    qctx = make_quote_ctx(load_config())
    q = get_quote(qctx, symbol)
    intent = _build_more_aggressive_sell_intent(symbol, qty, attempt=attempt, quote_last=q.last, bid=q.bid, ask=q.ask)
    if not intent:
        return False, 'no_intent', None

    r = submit_live_order(intent, dry_run=dry_run)
    if r.ok:
        return True, 'submitted', r.order_id
    return False, r.error or 'submit_failed', None
