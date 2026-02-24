"""Sync local OHLCV parquet store for watchlist.

Examples
  source venv/bin/activate
  python3 jobs/sync_store.py --tickers TSLA,KO,BABA,AAPL --interval 1h --days 120
  python3 jobs/sync_store.py --watchlist --interval 1d --days 500

Notes
- For 1H, running daily will accumulate >730d over time.
- For RS calculations, also sync 1D for SPY + tickers.
"""

from __future__ import annotations

import argparse

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from monitor.config import WATCHLIST
from data_store import sync_and_load


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", default="")
    ap.add_argument("--watchlist", action="store_true")
    ap.add_argument("--interval", default="1h", choices=["1h", "1d"])
    ap.add_argument("--days", type=int, default=120)
    ap.add_argument("--gap-threshold", type=int, default=7, help="auto-backfill if local gap exceeds N days")
    ap.add_argument("--max-auto-days", type=int, default=730, help="cap for auto-backfill lookback days")
    args = ap.parse_args()

    if args.watchlist:
        tickers = WATCHLIST
    else:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]

    if not tickers:
        raise SystemExit("No tickers provided. Use --tickers or --watchlist")

    # Always include SPY for RS baseline (1D)
    if args.interval == "1d" and "SPY" not in tickers:
        tickers = ["SPY"] + tickers

    for t in tickers:
        df = sync_and_load(
            t,
            interval=args.interval,
            lookback_days=args.days,
            # auto-backfill settings
            gap_days_threshold=args.gap_threshold,
            max_auto_lookback_days=args.max_auto_days,
        )
        print(f"{t:<8} {args.interval} rows={len(df):>6}  range={df.index.min()} -> {df.index.max()}")


if __name__ == "__main__":
    main()
