"""Test LongPort connection (quote + trade context).

Usage:
  cd /Users/vvusu/work/stock-strategy
  source venv/bin/activate
  export LONGPORT_APP_KEY=...
  export LONGPORT_APP_SECRET=...
  export LONGPORT_ACCESS_TOKEN=...
  python3 jobs/test_longport_connection.py
"""

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from broker.longport_client import load_config, make_quote_ctx, make_trade_ctx, get_quote


def main():
    cfg = load_config()
    qctx = make_quote_ctx(cfg)

    sym = 'TSLA.US'
    q = get_quote(qctx, sym)
    print('QUOTE', q)

    tctx = make_trade_ctx(cfg)
    print('TRADE_CTX_OK', type(tctx))


if __name__ == '__main__':
    main()
