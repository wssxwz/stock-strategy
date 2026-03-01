"""Read-only order helpers for LongPort."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Optional

from broker.longport_client import load_config, make_trade_ctx


@dataclass
class OrderSummary:
    order_id: str
    symbol: str
    side: str
    status: str
    qty: float | None = None
    filled_qty: float | None = None
    avg_price: float | None = None
    updated_at: str | None = None


def _get(obj, name, default=None):
    try:
        return getattr(obj, name)
    except Exception:
        return default


def _f(x):
    if x is None:
        return None
    try:
        return float(x)
    except Exception:
        return None


def list_today_orders() -> List[OrderSummary]:
    cfg = load_config()
    tctx = make_trade_ctx(cfg)
    resp = tctx.today_orders()

    # resp shape may vary; attempt common fields
    orders = _get(resp, 'orders', None)
    if orders is None and isinstance(resp, list):
        orders = resp
    if orders is None:
        return []

    out: List[OrderSummary] = []
    for o in orders:
        order_id = _get(o, 'order_id', None) or _get(o, 'id', None)
        sym = _get(o, 'symbol', None)
        side = str(_get(o, 'side', '') or '')
        status = str(_get(o, 'status', '') or '')
        qty = _f(_get(o, 'quantity', None) or _get(o, 'qty', None))
        filled_qty = _f(_get(o, 'filled_quantity', None) or _get(o, 'filled_qty', None))
        avg_price = _f(_get(o, 'average_price', None) or _get(o, 'avg_price', None))
        updated = _get(o, 'updated_at', None) or _get(o, 'update_time', None)
        out.append(OrderSummary(
            order_id=str(order_id) if order_id is not None else '',
            symbol=str(sym) if sym is not None else '',
            side=side,
            status=status,
            qty=qty,
            filled_qty=filled_qty,
            avg_price=avg_price,
            updated_at=str(updated) if updated is not None else None,
        ))
    return out


def get_order_detail(order_id: str) -> Any:
    cfg = load_config()
    tctx = make_trade_ctx(cfg)
    return tctx.order_detail(order_id)
