"""Mark a stop-out event (manual), set cooldown for a symbol.

Use this when you manually stop out a live position, until we have
full automatic sell + fill reconciliation.

Usage:
  source ~/.secrets/env/stock-strategy.live.env
  source venv/bin/activate
  python3 jobs/trade_stopout.py TSLA.US --hours 24 --reason "manual stop"
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from broker.cooldown import iso_after_hours
from broker.state_store import set_cooldown


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('symbol')
    ap.add_argument('--hours', type=float, default=float(os.environ.get('COOLDOWN_HOURS', '24')))
    ap.add_argument('--reason', default='stopout')
    args = ap.parse_args()

    until = iso_after_hours(args.hours)
    set_cooldown(args.symbol, until_iso=until, reason=args.reason)
    print(f"COOLDOWN_SET {args.symbol} until {until} reason={args.reason}")


if __name__ == '__main__':
    main()
