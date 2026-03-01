"""Fetch LongPort account snapshot (read-only).

Safety:
- Reads credentials from env (Config.from_env)
- Does NOT submit orders

Usage:
  source ~/.secrets/env/stock-strategy.env
  source venv/bin/activate
  python3 jobs/longport_account_snapshot.py
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
    # Decimal/float/int all fine
    try:
        return str(v)
    except Exception:
        return repr(v)


def print_balance_item(item, idx: int):
    print(f"--- balance[{idx}] ---")
    for k in [
        'currency',
        'net_assets',
        'total_cash',
        'buy_power',
        'max_finance_amount',
        'remaining_finance_amount',
        'init_margin',
        'maintenance_margin',
        'risk_level',
    ]:
        v = _get(item, k)
        if v is not None:
            print(f"{k}: {_fmt(v)}")

    cash_infos = _get(item, 'cash_infos')
    if cash_infos:
        for j, c in enumerate(cash_infos):
            print(f"  cash_infos[{j}] currency={_fmt(_get(c,'currency'))} avail={_fmt(_get(c,'available_cash'))} withdraw={_fmt(_get(c,'withdraw_cash'))} frozen={_fmt(_get(c,'frozen_cash'))} settling={_fmt(_get(c,'settling_cash'))}")


def main():
    cfg = load_config()
    tctx = make_trade_ctx(cfg)

    try:
        bal = tctx.account_balance()
    except Exception as e:
        print(f"account_balance failed: {e}")
        raise SystemExit(1)

    print('=== LongPort Account Balance (raw repr) ===')
    print(repr(bal))
    print('')
    print('=== Parsed (best-effort) ===')

    if isinstance(bal, list):
        for i, item in enumerate(bal):
            print_balance_item(item, i)
    else:
        print_balance_item(bal, 0)


if __name__ == '__main__':
    main()
