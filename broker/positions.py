"""Read-only positions helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from broker.longport_client import load_config, make_trade_ctx


@dataclass
class StockPos:
    symbol: str
    quantity: float | None = None
    market_value: float | None = None


def _get(obj, name):
    try:
        return getattr(obj, name)
    except Exception:
        return None


def _f(x):
    if x is None:
        return None
    try:
        return float(x)
    except Exception:
        return None


def fetch_stock_positions() -> List[StockPos]:
    cfg = load_config()
    tctx = make_trade_ctx(cfg)
    resp = tctx.stock_positions()

    # resp may be StockPositionsResponse { channels: [...] }
    channels = _get(resp, 'channels')
    out: List[StockPos] = []
    if channels:
        for ch in channels:
            positions = _get(ch, 'positions') or []
            for p in positions:
                sym = _get(p, 'symbol') or _get(p, 'code')
                if not sym:
                    continue
                out.append(
                    StockPos(
                        symbol=str(sym),
                        quantity=_f(_get(p, 'quantity') or _get(p, 'qty')),
                        market_value=_f(_get(p, 'market_value') or _get(p, 'market_val')),
                    )
                )
        return out

    # fallback: if resp itself is list
    if isinstance(resp, list):
        for p in resp:
            sym = _get(p, 'symbol') or _get(p, 'code')
            if sym:
                out.append(StockPos(symbol=str(sym)))
    return out
