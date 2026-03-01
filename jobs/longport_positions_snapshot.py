"""Fetch LongPort positions snapshot (read-only).

Usage:
  source ~/.secrets/env/stock-strategy.env
  source venv/bin/activate
  python3 jobs/longport_positions_snapshot.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from broker.longport_client import load_config, make_trade_ctx


def _get(obj, name):
    try:
        return getattr(obj, name)
    except Exception:
        return None


def _fmt(v):
    if v is None:
        return '-'
    try:
        return str(v)
    except Exception:
        return repr(v)


def main():
    cfg = load_config()
    tctx = make_trade_ctx(cfg)

    # stock positions
    try:
        pos = tctx.stock_positions()
    except Exception as e:
        print(f"stock_positions failed: {e}")
        pos = None

    if pos is None:
        return

    print('=== LongPort Stock Positions (raw repr) ===')
    print(repr(pos))
    print('')
    print('=== Parsed (best-effort) ===')

    if isinstance(pos, list):
        items = pos
    else:
        items = [pos]

    for i, p in enumerate(items):
        symbol = _get(p, 'symbol') or _get(p, 'stock') or _get(p, 'code')
        qty = _get(p, 'quantity') or _get(p, 'qty')
        cost = _get(p, 'cost_price') or _get(p, 'cost')
        mkt = _get(p, 'market_value') or _get(p, 'market_val')
        pl = _get(p, 'unrealized_pl') or _get(p, 'pl')
        print(f"[{i}] {symbol} qty={_fmt(qty)} cost={_fmt(cost)} mkt={_fmt(mkt)} upl={_fmt(pl)}")


if __name__ == '__main__':
    main()
