"""Read-only account helpers for LongPort.

All values are returned in a best-effort way.
We prefer USD available cash for sizing US-stock trading.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from broker.longport_client import make_trade_ctx, load_config


@dataclass
class CashSnapshot:
    currency: str
    available_cash: Optional[float] = None
    withdraw_cash: Optional[float] = None
    settling_cash: Optional[float] = None
    frozen_cash: Optional[float] = None


def _f(x) -> Optional[float]:
    if x is None:
        return None
    try:
        return float(x)
    except Exception:
        return None


def get_available_cash(currency: str = 'USD') -> Optional[float]:
    """Return available_cash for a given currency from account_balance."""
    cfg = load_config()
    tctx = make_trade_ctx(cfg)
    bal = tctx.account_balance()

    items = bal if isinstance(bal, list) else [bal]
    cur = (currency or '').upper()

    for item in items:
        cash_infos = getattr(item, 'cash_infos', None)
        if not cash_infos:
            continue
        for c in cash_infos:
            if (getattr(c, 'currency', '') or '').upper() == cur:
                return _f(getattr(c, 'available_cash', None))

    return None
