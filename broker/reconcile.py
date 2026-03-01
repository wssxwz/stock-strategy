"""Reconcile local trading_state.open_positions with broker live positions.

Goal: prevent drift when orders partially fill, fail, or manual trades happen.

Rules (conservative):
- If broker has no position for symbol -> remove local open_position
- If broker has position but local missing -> create local stub (entry/sl/tp unknown)

We do not guess SL/TP for broker-only positions.
"""

from __future__ import annotations

from typing import Dict, Any

from broker.positions import fetch_stock_positions
from broker.state_store import load_state, save_state


def reconcile_open_positions() -> Dict[str, Any]:
    st = load_state()
    local = st.get('open_positions') or {}

    broker_pos = fetch_stock_positions()
    broker_syms = {p.symbol.upper(): p for p in broker_pos if p.symbol}

    removed = []
    added = []

    # remove locals not in broker
    for sym in list(local.keys()):
        if sym.upper() not in broker_syms:
            removed.append(sym)
            local.pop(sym, None)

    # add broker positions not in local
    for sym_u, p in broker_syms.items():
        if sym_u not in {k.upper() for k in local.keys()}:
            added.append(p.symbol)
            local[p.symbol] = {
                'qty': p.quantity,
                'entry': None,
                'sl': None,
                'tp': None,
                'at': 'reconciled',
                'meta': {'source': 'broker_reconcile'}
            }

    st['open_positions'] = local
    save_state(st)

    return {'removed': removed, 'added': added, 'broker_count': len(broker_syms), 'local_count': len(local)}
