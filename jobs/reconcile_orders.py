"""Reconcile pending orders with broker / dry-run fills."""

from __future__ import annotations

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from broker.order_tracker import reconcile_pending_orders


def main():
    hours = float(os.environ.get('COOLDOWN_HOURS', '24'))
    r = reconcile_pending_orders(cooldown_hours=hours)
    print('ORDER_RECONCILE', r)


if __name__ == '__main__':
    main()
