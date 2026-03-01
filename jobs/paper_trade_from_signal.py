"""One-shot paper trade from a single signal json (debug helper)."""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from broker.longport_client import load_config, make_quote_ctx, get_quote
from broker.order_router import build_order_intent, PaperTradeConfig
from broker.paper_executor import append_ledger


def main():
    if len(sys.argv) < 2:
        print('Usage: python3 jobs/paper_trade_from_signal.py <signal.json>')
        raise SystemExit(2)

    sig = json.load(open(sys.argv[1]))

    cfg = PaperTradeConfig(equity=float(os.environ.get('PAPER_EQUITY', '100000')))

    lp_symbol = sig.get('ticker', '')
    # For quotes we need .US; the router maps, but quote helper expects it too.
    # We'll just pass mapped symbol through the router quote step by calling longport quote with .US.

    qctx = make_quote_ctx(load_config())

    # map symbol
    from broker.symbol_map import to_longport_symbol
    sym = to_longport_symbol(lp_symbol)

    q = get_quote(qctx, sym)
    intent = build_order_intent(sig, quote={'last': q.last, 'bid': q.bid, 'ask': q.ask}, cfg=cfg)
    print('INTENT', intent)
    if intent:
        append_ledger(intent, fill_price=intent.limit_price, status='FILLED')
        print('LEDGER appended')


if __name__ == '__main__':
    main()
