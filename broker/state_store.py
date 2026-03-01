"""Local trading state store (idempotency, daily limits, cooldown).

Stored under data/trades/ (gitignored).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict

STATE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'trades', 'trading_state.json')


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def load_state() -> Dict[str, Any]:
    try:
        with open(STATE_PATH, 'r') as f:
            return json.load(f)
    except Exception:
        return {
            'version': 1,
            'updated_at': _now_iso(),
            'executed_keys': {},
            'daily': {},
            'cooldowns': {},
            'open_positions': {},
            'pending_orders': {},
        }


def save_state(state: Dict[str, Any]):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    state['updated_at'] = _now_iso()
    with open(STATE_PATH, 'w') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def mark_executed(key: str, meta: Dict[str, Any] | None = None):
    st = load_state()
    st.setdefault('executed_keys', {})[key] = {
        'at': _now_iso(),
        'meta': meta or {},
    }
    save_state(st)


def was_executed(key: str) -> bool:
    st = load_state()
    return key in (st.get('executed_keys') or {})


def daily_count(day_key: str) -> int:
    st = load_state()
    return int((st.get('daily') or {}).get(day_key, 0) or 0)


def inc_daily(day_key: str):
    st = load_state()
    d = st.setdefault('daily', {})
    d[day_key] = int(d.get(day_key, 0) or 0) + 1
    save_state(st)


def set_cooldown(symbol: str, until_iso: str, reason: str):
    st = load_state()
    st.setdefault('cooldowns', {})[symbol] = {'until': until_iso, 'reason': reason}
    save_state(st)


def cooldown_active(symbol: str) -> tuple[bool, str]:
    st = load_state()
    cd = (st.get('cooldowns') or {}).get(symbol)
    if not cd:
        return False, ''
    until = cd.get('until')
    if not until:
        return False, ''
    try:
        t_until = datetime.fromisoformat(until)
    except Exception:
        return False, ''
    if datetime.now(timezone.utc) < t_until:
        return True, cd.get('reason') or ''
    return False, ''


def add_open_position(symbol: str, qty: float, entry: float, sl: float | None, tp: float | None, meta: Dict[str, Any] | None = None):
    st = load_state()
    st.setdefault('open_positions', {})[symbol] = {
        'qty': qty,
        'entry': entry,
        'sl': sl,
        'tp': tp,
        'at': _now_iso(),
        'meta': meta or {},
    }
    save_state(st)


def remove_open_position(symbol: str):
    st = load_state()
    ops = st.setdefault('open_positions', {})
    if symbol in ops:
        ops.pop(symbol, None)
        save_state(st)


def total_open_risk_usd() -> float:
    st = load_state()
    ops = st.get('open_positions') or {}
    total = 0.0
    for sym, rec in ops.items():
        try:
            qty = float(rec.get('qty') or 0)
            entry = float(rec.get('entry') or 0)
            sl = rec.get('sl')
            if sl is None:
                continue
            sl = float(sl)
            total += max(0.0, (entry - sl) * qty)
        except Exception:
            continue
    return total


# --- order tracking ---

def add_pending_order(order_id: str, record: Dict[str, Any]):
    st = load_state()
    st.setdefault('pending_orders', {})[order_id] = {
        **(record or {}),
        'updated_at': _now_iso(),
    }
    save_state(st)


def update_pending_order(order_id: str, patch: Dict[str, Any]):
    st = load_state()
    po = st.setdefault('pending_orders', {})
    cur = po.get(order_id) or {}
    cur.update(patch or {})
    cur['updated_at'] = _now_iso()
    po[order_id] = cur
    save_state(st)


def remove_pending_order(order_id: str):
    st = load_state()
    po = st.setdefault('pending_orders', {})
    if order_id in po:
        po.pop(order_id, None)
        save_state(st)


def list_pending_orders() -> Dict[str, Any]:
    st = load_state()
    return st.get('pending_orders') or {}
