"""Order tracking & reconciliation.

We store pending orders in local trading_state.pending_orders (gitignored).
On each scan, we can:
- mark dry-run orders as filled immediately (simulation)
- for real orders, best-effort match by order_id using today_orders/order_detail

This module is intentionally conservative.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Dict, Any

from broker.orders import list_today_orders, get_order_detail
from broker.state_store import (
    list_pending_orders, update_pending_order, remove_pending_order,
    add_open_position, remove_open_position, set_cooldown,
)
from broker.cooldown import iso_after_hours


def reconcile_pending_orders(*, cooldown_hours: float = 24.0) -> Dict[str, Any]:
    pending = list_pending_orders()
    if not pending:
        return {'pending': 0, 'updated': 0, 'removed': 0}

    # Dry-run orders: mark filled immediately
    updated = 0
    removed = 0

    # pull today's orders once (best-effort)
    today = []
    try:
        today = list_today_orders()
    except Exception:
        today = []

    today_map = {o.order_id: o for o in today if o.order_id}

    for oid, rec in list(pending.items()):
        if oid.startswith('DRYRUN-'):
            # simulate fill
            if rec.get('status') != 'FILLED':
                update_pending_order(oid, {'status': 'FILLED'})
                updated += 1

            # apply position state transitions
            side = (rec.get('side') or '').lower()
            symbol = rec.get('symbol')
            qty = rec.get('qty')
            limit_price = rec.get('limit_price')
            sl = rec.get('sl')
            tp = rec.get('tp')

            try:
                if side == 'buy':
                    add_open_position(symbol, qty, float(limit_price or 0), sl, tp, meta={'source': 'dryrun_fill'})
                elif side == 'sell':
                    remove_open_position(symbol)
                    if rec.get('reason') in ('STOP_LOSS','止损'):
                        set_cooldown(symbol, until_iso=iso_after_hours(cooldown_hours), reason='stopout')
            except Exception:
                pass

            remove_pending_order(oid)
            removed += 1
            continue

        # real orders: match by order_id if present in today_orders
        summ = today_map.get(oid)
        if summ is None:
            # keep pending; could be older than today; optionally order_detail
            continue

        patch = {
            'status': summ.status,
            'filled_qty': summ.filled_qty,
            'avg_price': summ.avg_price,
        }
        update_pending_order(oid, patch)
        updated += 1

        # If status indicates completion, apply transitions (best-effort)
        st = (summ.status or '').upper()
        if st in {'FILLED', 'DONE', 'SUCCESS'}:
            side = (rec.get('side') or '').lower()
            symbol = rec.get('symbol')
            qty = rec.get('qty')
            avg = summ.avg_price or rec.get('limit_price')
            sl = rec.get('sl')
            tp = rec.get('tp')
            try:
                if side == 'buy':
                    add_open_position(symbol, qty, float(avg or 0), sl, tp, meta={'source': 'broker_fill', 'order_id': oid})
                elif side == 'sell':
                    remove_open_position(symbol)
                    if rec.get('reason') in ('STOP_LOSS','止损'):
                        set_cooldown(symbol, until_iso=iso_after_hours(cooldown_hours), reason='stopout')
            except Exception:
                pass

            remove_pending_order(oid)
            removed += 1

        elif st in {'CANCELED', 'CANCELLED', 'REJECTED', 'FAILED'}:
            remove_pending_order(oid)
            removed += 1

    return {'pending': len(pending), 'updated': updated, 'removed': removed}
