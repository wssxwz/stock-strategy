"""Reconcile local trading state with broker positions (read-only).

Usage:
  source ~/.secrets/env/stock-strategy.live.env
  source venv/bin/activate
  python3 jobs/reconcile_trading_state.py
"""

from __future__ import annotations

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from broker.reconcile import reconcile_open_positions


def main():
    r = reconcile_open_positions()
    print('RECONCILE', r)


if __name__ == '__main__':
    main()
