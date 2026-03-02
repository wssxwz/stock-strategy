"""Order tracking & reconciliation.

We store pending orders in local trading_state.pending_orders (gitignored).

Reconciliation sources:
- Dry-run: mark as filled immediately
- Live: use today_orders() best-effort; if missing, try order_detail(order_id)

State transitions:
- BUY filled -> add_open_position(symbol, qty, entry=avg_price, sl/tp)
- SELL filled -> remove_open_position(symbol) (+ stopout cooldown for STOP_LOSS)

Partial fills:
- If filled_qty is present and >0, update open_position qty (best-effort) when BUY.
"""

from __future__ import annotations

from typing import Dict, Any

from broker.orders import list_today_orders, get_order_detail, normalize_status
from broker.state_store import (
    list_pending_orders, update_pending_order, remove_pending_order,
    add_open_position, remove_open_position, set_cooldown,
)
from broker.cooldown import iso_after_hours


_FINAL_FILLED = {'FILLED', 'DONE', 'SUCCESS', 'FILLED_ALL'}
_FINAL_CANCEL = {'CANCELED', 'CANCELLED', 'REJECTED', 'FAILED', 'EXPIRED'}


def _detail_extract(detail: Any) -> dict:
    # best-effort extract fields from order_detail response
    def g(name, default=None):
        try:
            return getattr(detail, name)
        except Exception:
            return default
    def f(x):
        try:
            return float(x)
        except Exception:
            return None
    return {
        'status': normalize_status(g('status', '')),
        'filled_qty': f(g('filled_quantity', None) or g('filled_qty', None)),
        'avg_price': f(g('average_price', None) or g('avg_price', None) or g('avg_done_price', None)),
    }


def reconcile_pending_orders(*, cooldown_hours: float = 24.0) -> Dict[str, Any]:
    pending = list_pending_orders()
    if not pending:
        return {'pending': 0, 'updated': 0, 'removed': 0}

    updated = 0
    removed = 0

    today = []
    try:
        today = list_today_orders()
    except Exception:
        today = []
    today_map = {o.order_id: o for o in today if o.order_id}

    for oid, rec in list(pending.items()):
        # Dry-run orders: mark filled immediately
        if str(oid).startswith('DRYRUN-'):
            if rec.get('status') != 'FILLED':
                update_pending_order(oid, {'status': 'FILLED'})
                updated += 1

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
                    if rec.get('reason') in ('STOP_LOSS', '止损', 'STOP_LOSS_ESCALATE'):
                        set_cooldown(symbol, until_iso=iso_after_hours(cooldown_hours), reason='stopout')
            except Exception:
                pass

            remove_pending_order(oid)
            removed += 1
            continue

        # Live orders
        summ = today_map.get(oid)
        status = None
        filled_qty = None
        avg_price = None

        if summ is not None:
            status = summ.status
            filled_qty = summ.filled_qty
            avg_price = summ.avg_price
        else:
            # fallback: order_detail
            try:
                detail = get_order_detail(oid)
                dd = _detail_extract(detail)
                status = dd.get('status')
                filled_qty = dd.get('filled_qty')
                avg_price = dd.get('avg_price')
            except Exception:
                status = None

        if status is None:
            continue

        patch = {'status': status, 'filled_qty': filled_qty, 'avg_price': avg_price}
        update_pending_order(oid, patch)
        updated += 1

        st = (status or '').upper()
        if st in _FINAL_FILLED:
            side = (rec.get('side') or '').lower()
            symbol = rec.get('symbol')
            qty = rec.get('qty')
            sl = rec.get('sl')
            tp = rec.get('tp')
            entry = avg_price or rec.get('limit_price')

            try:
                if side == 'buy':
                    # If partial fill info exists, prefer it.
                    q_eff = filled_qty if (filled_qty is not None and filled_qty > 0) else qty
                    add_open_position(symbol, q_eff, float(entry or 0), sl, tp, meta={'source': 'broker_fill', 'order_id': oid})
                elif side == 'sell':
                    remove_open_position(symbol)
                    if rec.get('reason') in ('STOP_LOSS', '止损', 'STOP_LOSS_ESCALATE'):
                        set_cooldown(symbol, until_iso=iso_after_hours(cooldown_hours), reason='stopout')
            except Exception:
                pass

            remove_pending_order(oid)
            removed += 1

        elif st in _FINAL_CANCEL:
            remove_pending_order(oid)
            removed += 1

    return {'pending': len(pending), 'updated': updated, 'removed': removed}
