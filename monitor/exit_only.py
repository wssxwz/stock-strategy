"""Exit-only monitor for higher frequency risk control.

Purpose:
- Run frequently (e.g., every 10 minutes) during market hours
- Only checks existing open positions (local state + broker reconcile)
- Triggers STOP_LOSS / TAKE_PROFIT exits using LongPort quotes
- Uses hard live guards; defaults to dry-run unless LIVE_SUBMIT=1

This avoids the cost/noise of full market scans.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from broker.trading_env import is_live, live_trading_enabled


def main():
    if not (is_live() and live_trading_enabled()):
        print('EXIT_ONLY: live trading not enabled (TRADING_ENV=live & LIVE_TRADING=YES_I_KNOW required).')
        return

    # 0) reconcile pending orders (dry-run fills / broker updates)
    try:
        from broker.order_tracker import reconcile_pending_orders
        hours = float(os.environ.get('COOLDOWN_HOURS', '24'))
        rr = reconcile_pending_orders(cooldown_hours=hours)
        if rr.get('updated') or rr.get('removed'):
            print(f"\n[ORDER_RECONCILE] updated={rr.get('updated')} removed={rr.get('removed')}")
    except Exception as e:
        print(f"  [order-reconcile failed] {e}")

    # 1) reconcile open_positions with broker positions
    try:
        from broker.reconcile import reconcile_open_positions
        rrec = reconcile_open_positions()
        if rrec.get('removed') or rrec.get('added'):
            print(f"\n[RECONCILE] added={len(rrec.get('added',[]))} removed={len(rrec.get('removed',[]))}")
    except Exception as e:
        print(f"  [reconcile failed] {e}")

    # 2) state-based exit monitor
    try:
        from broker.state_store import load_state as load_trading_state, set_cooldown, remove_open_position, add_pending_order
        from broker.exit_monitor import check_open_positions
        from broker.longport_client import load_config, make_quote_ctx, get_quote
        from broker.exit_router import build_exit_intent
        from broker.positions import fetch_stock_positions
        from broker.live_executor import submit_live_order
        from broker.paper_executor import append_ledger
        from broker.cooldown import iso_after_hours

        tstate = load_trading_state()
        open_pos = (tstate.get('open_positions') or {})
        if not open_pos:
            print('EXIT_ONLY: no open_positions in local state.')
            return

        qctx = make_quote_ctx(load_config())

        quotes = {}
        for sym in list(open_pos.keys()):
            q = get_quote(qctx, sym)
            if q.last is not None:
                quotes[sym] = q.last

        events = check_open_positions(open_pos, quotes)
        if not events:
            print('EXIT_ONLY: no exit events.')
            return

        qty_map = {}
        for pos in fetch_stock_positions():
            try:
                qty_map[pos.symbol.upper()] = int(float(pos.quantity or 0))
            except Exception:
                pass

        for ev in events:
            # EXIT_ESCALATE: if STOP_LOSS and we already have a pending SELL, cancel/replace more aggressively
            try:
                from broker.state_store import list_pending_orders, get_exit_escalation_attempt, inc_exit_escalation_attempt
                pending = list_pending_orders()
                has_pending_sell = False
                pending_ids = []
                for oid, rec in pending.items():
                    if (rec.get('symbol') or '').upper() == ev.symbol.upper() and (rec.get('side') or '').lower() == 'sell':
                        has_pending_sell = True
                        pending_ids.append(oid)
                if ev.kind == 'STOP_LOSS' and has_pending_sell:
                    attempt = get_exit_escalation_attempt(ev.symbol)
                    max_attempts = int(os.environ.get('EXIT_ESCALATE_MAX_ATTEMPTS', '3'))
                    if attempt < max_attempts:
                        # cancel all pending sell orders for this symbol
                        try:
                            from broker.exit_escalator import cancel_order, escalate_stop_loss_sell
                            for oid in pending_ids:
                                cancel_order(oid)
                        except Exception:
                            pass

                        dry_run = (os.environ.get('LIVE_SUBMIT', '0') != '1')
                        ok, msg, new_oid = (False, 'skip', None)
                        try:
                            ok, msg, new_oid = escalate_stop_loss_sell(ev.symbol, qty, attempt=attempt, dry_run=dry_run)
                        except Exception as e:
                            ok, msg, new_oid = (False, str(e), None)

                        inc_exit_escalation_attempt(ev.symbol)
                        if ok:
                            if new_oid:
                                try:
                                    add_pending_order(new_oid, {
                                        'symbol': ev.symbol,
                                        'side': 'Sell',
                                        'qty': qty,
                                        'limit_price': None,
                                        'reason': 'STOP_LOSS_ESCALATE',
                                        'status': 'PENDING',
                                    })
                                except Exception:
                                    pass
                            print(f"\nLIVE_EXIT_ESCALATE_{'DRYRUN' if dry_run else 'SUBMIT'}:{ev.symbol}:attempt={attempt}")
                        else:
                            print(f"\nLIVE_EXIT_ESCALATE_FAIL:{ev.symbol}:{msg}")
                        continue  # do not place the normal exit order in same tick
            except Exception as e:
                # escalation is best-effort; fall back to normal exit intent
                pass

            qty = qty_map.get(ev.symbol.upper(), 0)
            if qty <= 0:
                continue

            q = get_quote(qctx, ev.symbol)
            intent = build_exit_intent(ev.symbol, qty, quote={'last': q.last, 'bid': q.bid, 'ask': q.ask}, reason=ev.kind)
            if not intent:
                continue

            append_ledger(intent, fill_price=intent.limit_price, status='PENDING')
            dry_run = (os.environ.get('LIVE_SUBMIT', '0') != '1')
            r = submit_live_order(intent, dry_run=dry_run)

            if r.order_id:
                try:
                    add_pending_order(r.order_id, {
                        'symbol': intent.symbol,
                        'side': intent.side,
                        'qty': intent.qty,
                        'limit_price': intent.limit_price,
                        'reason': ev.kind,
                        'status': 'PENDING',
                    })
                except Exception:
                    pass

            if r.ok and r.dry_run:
                print(f"\nLIVE_EXIT_DRYRUN:{intent.symbol}:{intent.side}:{intent.qty}@{intent.limit_price}")
            elif r.ok:
                print(f"\nLIVE_EXIT_OK:{intent.symbol}:order_id={r.order_id}")
                try:
                    remove_open_position(intent.symbol)
                except Exception:
                    pass
                if ev.kind == 'STOP_LOSS':
                    hours = float(os.environ.get('COOLDOWN_HOURS', '24'))
                    set_cooldown(intent.symbol, until_iso=iso_after_hours(hours), reason='stopout')
            else:
                print(f"\nLIVE_EXIT_FAIL:{intent.symbol}:{r.error}")

    except Exception as e:
        print(f"  [exit-only failed] {e}")


if __name__ == '__main__':
    main()
