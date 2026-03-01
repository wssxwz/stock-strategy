import os
"""
完整扫描主程序（买入 + 卖出双向提醒）
由 OpenClaw cron 每小时调用
"""
import sys, os, json, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../src'))

import yfinance as yf
from datetime import datetime, timedelta

# local store (parquet) for faster/reproducible data
try:
    from data_store import sync_and_load
except Exception:
    sync_and_load = None
from fast_scan import phase1_filter, phase2_score
from portfolio import load_portfolio, check_positions, format_exit_alert
from signal_engine import format_signal_message
from config import WATCHLIST, NOTIFY
from market_regime import get_market_regime, regime_header, get_score_threshold

STATE_FILE = os.path.join(os.path.dirname(__file__), '.monitor_state.json')

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            s = json.load(f)
            # backward-compatible defaults
            s.setdefault('sent_signals', {})
            s.setdefault('no_signal_streak', 0)  # consecutive scans with NO_SIGNAL
            return s
    return {'sent_signals': {}, 'no_signal_streak': 0}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2, default=str)

def signal_key(sig):
    date_str = datetime.now().strftime('%Y-%m-%d')
    return f"{sig['ticker']}_{date_str}_{sig['score']//10*10}"

def get_current_prices(tickers: list) -> dict:
    """批量获取当前价格

    Priority:
    - Use local 1h store last close when available (fast + stable)
    - Fallback to yfinance download (1m)
    """
    prices: dict = {}
    if not tickers:
        return prices

    # 1) local store
    if sync_and_load is not None:
        try:
            for t in tickers:
                df = sync_and_load(t, interval='1h', lookback_days=7)
                if df is not None and not df.empty and 'close' in df.columns:
                    prices[t] = float(df['close'].iloc[-1])
        except Exception:
            pass

    # 2) fallback yfinance for missing
    missing = [t for t in tickers if t not in prices]
    if not missing:
        return prices

    try:
        data = yf.download(missing, period='1d', interval='1m',
                           auto_adjust=True, progress=False, threads=True)
        if len(missing) == 1:
            prices[missing[0]] = float(data['Close'].iloc[-1])
        else:
            for t in missing:
                try:
                    prices[t] = float(data['Close'][t].iloc[-1])
                except Exception:
                    pass
    except Exception as e:
        print(f"  价格获取失败: {e}")
    return prices


def main():
    state = load_state()
    output_lines = []

    # Live order tracking reconciliation (dry-run fills / broker status)
    try:
        from broker.trading_env import is_live, live_trading_enabled
        if is_live() and live_trading_enabled():
            from broker.order_tracker import reconcile_pending_orders
            hours = float(os.environ.get('COOLDOWN_HOURS', '24'))
            rr = reconcile_pending_orders(cooldown_hours=hours)
            if rr.get('updated') or rr.get('removed'):
                print(f"\n[ORDER_RECONCILE] updated={rr.get('updated')} removed={rr.get('removed')}")
    except Exception as _oe:
        print(f"  [order-reconcile failed] {_oe}")

    # Live state-based exit monitor (preferred for automation)
    try:
        from broker.trading_env import is_live, live_trading_enabled
        if is_live() and live_trading_enabled():
            from broker.state_store import load_state as _load_trading_state
            from broker.exit_monitor import check_open_positions
            from broker.longport_client import load_config, make_quote_ctx, get_quote
            from broker.exit_router import build_exit_intent
            from broker.live_executor import submit_live_order
            from broker.paper_executor import append_ledger
            from broker.positions import fetch_stock_positions
            from broker.state_store import remove_open_position, set_cooldown
            from broker.cooldown import iso_after_hours

            tstate = _load_trading_state()
            open_pos = (tstate.get('open_positions') or {})

            if open_pos:
                qctx = make_quote_ctx(load_config())
                # fetch last quotes
                quotes = {}
                for sym in list(open_pos.keys()):
                    q = get_quote(qctx, sym)
                    if q.last is not None:
                        quotes[sym] = q.last

                events = check_open_positions(open_pos, quotes)

                # map quantities from live positions
                qty_map = {}
                for pos in fetch_stock_positions():
                    try:
                        qty_map[pos.symbol.upper()] = int(float(pos.quantity or 0))
                    except Exception:
                        pass

                for ev in events:
                    qty = qty_map.get(ev.symbol.upper(), 0)
                    if qty <= 0:
                        continue

                    # build & submit exit intent
                    q = get_quote(qctx, ev.symbol)
                    intent = build_exit_intent(ev.symbol, qty, quote={'last': q.last, 'bid': q.bid, 'ask': q.ask}, reason=ev.kind)
                    if not intent:
                        skip_reasons.append((lp_symbol, f"{reason}", key))
                        continue

                    append_ledger(intent, fill_price=intent.limit_price, status='PENDING')
                    dry_run = (os.environ.get('LIVE_SUBMIT', '0') != '1')
                    r = submit_live_order(intent, dry_run=dry_run)
                    try:
                        from broker.state_store import add_pending_order
                        if r.order_id:
                            add_pending_order(r.order_id, {
                                "symbol": intent.symbol,
                                "side": intent.side,
                                "qty": intent.qty,
                                "limit_price": intent.limit_price,
                                "reason": ev.kind,
                                "status": "PENDING",
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
    except Exception as _e:
        print(f"  [live-exit-monitor failed] {_e}")

    # ════════════════════════════════════
    # 第一部分：检查持仓止盈止损
    # ════════════════════════════════════

    # SKIP_LEGACY_PORTFOLIO: in live automation we rely on broker positions + open_positions state
    try:
        from broker.trading_env import is_live, live_trading_enabled
        if is_live() and live_trading_enabled():
            portfolio = {}
        else:
            portfolio = load_portfolio()
    except Exception:
        portfolio = load_portfolio()
    if portfolio:
        print(f"\n[持仓检查] {len(portfolio)} 只持仓...")
        held_tickers = list(portfolio.keys())
        current_prices = get_current_prices(held_tickers)

        exit_alerts = check_positions(current_prices)
        for alert in exit_alerts:
            msg = format_exit_alert(alert)
            print(f"\nEXIT_SIGNAL:{alert['ticker']}:{alert['type']}")
            print(msg)
            print("---END---")
            output_lines.append(f"EXIT_SIGNAL:{alert['ticker']}:{alert['type']}")
            output_lines.append(msg)
            output_lines.append("---END---")

            # Live exit execution (hard-gated). Stop-loss exits set cooldown.
            try:
                from broker.trading_env import is_live, live_trading_enabled
                if is_live() and live_trading_enabled():
                    from broker.symbol_map import to_longport_symbol
                    from broker.longport_client import load_config, make_quote_ctx, get_quote
                    from broker.positions import fetch_stock_positions
                    from broker.exit_router import build_exit_intent
                    from broker.live_executor import submit_live_order
                    from broker.paper_executor import append_ledger
                    from broker.state_store import remove_open_position, set_cooldown
                    from broker.cooldown import iso_after_hours

                    sym = to_longport_symbol(alert.get('ticker'))

                    qty = 0
                    for pos in fetch_stock_positions():
                        if (pos.symbol or '').upper() == sym.upper():
                            try:
                                qty = int(float(pos.quantity or 0))
                            except Exception:
                                qty = 0
                            break

                    if qty > 0:
                        qctx = make_quote_ctx(load_config())
                        q = get_quote(qctx, sym)
                        intent = build_exit_intent(sym, qty, quote={'last': q.last, 'bid': q.bid, 'ask': q.ask}, reason=alert.get('type','exit'))
                        if intent:
                            append_ledger(intent, fill_price=intent.limit_price, status='PENDING')
                            dry_run = (os.environ.get('LIVE_SUBMIT', '0') != '1')
                            r = submit_live_order(intent, dry_run=dry_run)
                            try:
                                from broker.state_store import add_pending_order
                                if r.order_id:
                                    add_pending_order(r.order_id, {
                                        'symbol': intent.symbol,
                                        'side': intent.side,
                                        'qty': intent.qty,
                                        'limit_price': intent.limit_price,
                                        'reason': (alert.get('type') or 'EXIT'),
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
                                if alert.get('type') == '止损':
                                    hours = float(os.environ.get('COOLDOWN_HOURS', '24'))
                                    set_cooldown(intent.symbol, until_iso=iso_after_hours(hours), reason='stopout')
                            else:
                                print(f"\nLIVE_EXIT_FAIL:{intent.symbol}:{r.error}")
            except Exception as _ex:
                print(f"  [live-exit failed] {_ex}")
    else:
        print("[持仓检查] 无持仓记录，跳过")

    # ════════════════════════════════════
    # 第二部分：市场环境识别
    # ════════════════════════════════════
    regime = get_market_regime()
    effective_min_score = regime['min_score']
    print(f"\n[市场环境] {regime['detail']}")
    print(f"[信号阈值] score≥{effective_min_score}（{'正常' if regime['regime']=='bull' else '已上调'}）")

    if not regime['signal_allowed']:
        print(f"\n⛔ 当前为{regime['regime_zh']}模式，暂停买入信号扫描")
        save_state(state)
        return

    # ════════════════════════════════════
    # 第三部分：扫描买入信号
    # ════════════════════════════════════

    # ret5 动态降级（KO 低波动票也要有出手机会）
    # 全市场连续无信号 >=20 / >=30 / >=40: 逐步放宽 ret5 门槛
    streak = int(state.get('no_signal_streak', 0) or 0)
    if streak >= 30:
        ret5_entry_pct = -2.0
        ret5_level = 'L2'
    elif streak >= 20:
        ret5_entry_pct = -2.5
        ret5_level = 'L1'
    else:
        ret5_entry_pct = -3.0
        ret5_level = 'L0'
    print(f"[ret5 门槛] {ret5_level}: ret_5d ≤ {ret5_entry_pct:.1f}%（无信号连续 {streak} 次）")
    print(f"\n[买入扫描] 开始扫描 {len(WATCHLIST)} 只股票...")
    candidates = phase1_filter(WATCHLIST)
    # phase2_score 后按动态阈值过滤（P3：按股票类型细化阈值）
    buy_signals_raw = phase2_score(candidates) if candidates else []

    # 先按 ret5 硬门槛过滤（动态降级）
    buy_signals_ret5 = []
    for s in buy_signals_raw:
        try:
            # signal_engine 的 ret_5d 是百分比口径（例如 -2.3）
            if float(s.get('ret_5d', 0)) <= ret5_entry_pct:
                buy_signals_ret5.append(s)
        except Exception:
            continue

    # Execution router (MR vs STRUCT) — V3.1
    # 1) If structure 1buy/2buy exists AND above MA200 AND (chop not high / ATR not big) -> STRUCT
    # 2) Else if bb_pct < 0.10 (esp RSI<25) -> MR
    # 3) Else -> SKIP
    ATR_PCT14_MAX = 3.5  # percent (e.g. 3.5 means ATR%<=3.5%)

    routed = []
    for s in buy_signals_ret5:
        # defaults
        s['exec_mode'] = 'SKIP'
        s['exec_reason'] = ''

        bb = float(s.get('bb_pct', 0.5) or 0.5)
        rsi = float(s.get('rsi14', 50) or 50)
        above200 = bool(s.get('above_ma200', False))
        atr_pct14 = s.get('atr_pct14', None)
        try:
            atr_ok = (atr_pct14 is not None) and (float(atr_pct14) <= ATR_PCT14_MAX)
        except Exception:
            atr_ok = False

        st = s.get('structure') or {}
        st_signals = st.get('signals') or []
        st_best = st.get('best') or None

        if st_signals and st_best and above200 and atr_ok:
            s['exec_mode'] = 'STRUCT'
            s['exec_struct_type'] = st_best.get('type')
            s['exec_reason'] = f"STRUCT({s['exec_struct_type']}) ma200+ atr%<= {ATR_PCT14_MAX}"
        elif bb < 0.10:
            s['exec_mode'] = 'MR'
            s['exec_reason'] = f"MR bb<{0.10:.2f}" + (" rsi<25" if rsi < 25 else "")
        else:
            s['exec_mode'] = 'SKIP'
            s['exec_reason'] = 'skip: no-struct and bb>=0.10'

        # keep for later analysis
        s['atr_gate_max'] = ATR_PCT14_MAX
        routed.append(s)

    # Apply score threshold only to MR/STRUCT candidates
    buy_signals = []
    for s in routed:
        if s.get('exec_mode') == 'SKIP':
            continue
        ticker_threshold = get_score_threshold(s['ticker'], regime)
        s['score_threshold'] = ticker_threshold  # 记录该股实际阈值
        s['ret5_entry_pct'] = ret5_entry_pct
        s['ret5_level'] = ret5_level
        s['no_signal_streak'] = streak
        if s['score'] >= ticker_threshold:
            buy_signals.append(s)

    print(
        f"[信号过滤] 原始触发 {len(buy_signals_raw)} 只 → ret5通过 {len(buy_signals_ret5)} 只 → 路由通过 {sum(1 for x in routed if x.get('exec_mode')!='SKIP')} 只 → 达到阈值 {len(buy_signals)} 只"
    )

    new_buy = []
    for sig in buy_signals:
        # 附加市场环境信息到信号
        sig['market_regime']   = regime['regime']
        sig['market_regime_zh']= regime['regime_zh']
        sig['effective_score_threshold'] = effective_min_score
        key = signal_key(sig)
        if key not in state['sent_signals']:
            new_buy.append(sig)
            state['sent_signals'][key] = {
                'ticker': sig['ticker'], 'score': sig['score'],
                'price': sig['price'], 'time': datetime.now().isoformat()
            }

    # -------- Push strategy (noise reduction)
    # - Strong or STRUCT: send immediately (single message)
    # - Normal: send one batch summary message per scan
    strong_buy = []
    normal_buy = []
    for s in new_buy:
        is_strong = (float(s.get('score', 0) or 0) >= 85) or (s.get('exec_mode') == 'STRUCT')
        (strong_buy if is_strong else normal_buy).append(s)

    # Batch push_history raw includes full formatted messages for archival
    batch_raw = "\n\n".join([format_signal_message(sig) for sig in new_buy])
    if new_buy:
        batch_title = f"📣 全市场扫描信号（{datetime.now().strftime('%Y-%m-%d %H:%M')} 北京）"
        batch_summary = (
            f"✅ 买入 {len(new_buy)} / 卖出 0｜强信号 {len(strong_buy)} 只｜"
            f"{regime['regime_zh']}模式"
        )

    # --- 1) Send strong individually
    for sig in strong_buy:
        msg = format_signal_message(sig)
        print(f"\nBUY_SIGNAL:{sig['ticker']}:{sig['score']}")
        print(msg)
        print("---END---")
        output_lines.append(f"BUY_SIGNAL:{sig['ticker']}:{sig['score']}")
        output_lines.append(msg)
        output_lines.append("---END---")

        # Paper/Live execution selection (capital constrained)
        # - Build intents for all strong signals
        # - Apply idempotency, cooldown, daily limits, max open positions
        # - Select Top1 intent by execution score
        try:
            from broker.longport_client import load_config, make_quote_ctx, get_quote
            from broker.symbol_map import to_longport_symbol
            from broker.order_router import try_build_order_intent, PaperTradeConfig
            from broker.paper_executor import append_ledger
            from broker.intent_eval import compute_metrics
            from broker.trading_env import is_paper, is_live, live_trading_enabled
            from broker.state_store import was_executed, mark_executed, daily_count, inc_daily, cooldown_active, total_open_risk_usd, add_open_position
            from datetime import datetime

            # Switches / limits
            max_open_pos = int(os.environ.get('MAX_OPEN_POS', '1'))
            max_price_pct_equity = float(os.environ.get('MAX_PRICE_PCT_EQUITY', '0.35'))
            total_risk_cap_pct = float(os.environ.get('TOTAL_RISK_CAP', '0.02'))
            max_new_buys_per_day = int(os.environ.get('MAX_NEW_BUYS_PER_DAY', '1'))
            price_drift_max_pct = float(os.environ.get('PRICE_DRIFT_MAX_PCT', '0.015'))  # 1.5%

            # equity sizing base (USD) from broker
            equity = None
            try:
                from broker.account import get_available_cash
                equity = get_available_cash('USD')
            except Exception:
                equity = None
            if equity is None:
                equity = float(os.environ.get('PAPER_EQUITY', '100000'))

            # current open positions count (live)
            open_pos_count = 0
            if is_live():
                try:
                    from broker.positions import fetch_stock_positions
                    open_pos_count = len(fetch_stock_positions())
                except Exception:
                    open_pos_count = 0

                        # portfolio risk cap (USD)
            total_risk_cap_usd = equity * total_risk_cap_pct
            cur_risk = 0.0
            try:
                cur_risk = float(total_open_risk_usd())
            except Exception:
                cur_risk = 0.0

            # reconcile local open_positions with broker positions (prevents drift)
            try:
                from broker.reconcile import reconcile_open_positions
                rrec = reconcile_open_positions()
                if rrec.get('removed') or rrec.get('added'):
                    print(f"\n[RECONCILE] added={len(rrec.get('added',[]))} removed={len(rrec.get('removed',[]))}")
            except Exception as _re:
                print(f"  [reconcile failed] {_re}")

            # daily limits key (UTC date)
            day_key = datetime.utcnow().strftime('%Y-%m-%d')
            if daily_count(day_key) >= max_new_buys_per_day:
                # Already hit daily buy limit
                pass
            else:
                qctx = make_quote_ctx(load_config())
                candidates = []
                skip_reasons = []
                for s in strong_buy:
                    # cooldown / idempotency key
                    exec_mode = (s.get('exec_mode') or '').upper()
                    bar_time = s.get('bar_time') or s.get('bar_ts') or ''
                    key = f"{s.get('ticker')}|{exec_mode}|{bar_time}"
                    if was_executed(key):
                        skip_reasons.append((lp_symbol, "SKIP_IDEMPOTENT", key))
                        continue
                    lp_symbol = to_longport_symbol(s.get('ticker'))
                    # prevent duplicate buys while a buy is pending
                    try:
                        from broker.state_store import has_pending_symbol_side
                        if has_pending_symbol_side(lp_symbol, 'Buy'):
                            skip_reasons.append((lp_symbol, 'SKIP_PENDING_BUY', key))
                            continue
                    except Exception:
                        pass
                    cd_on, cd_reason = cooldown_active(lp_symbol)
                    if cd_on:
                        skip_reasons.append((lp_symbol, f"SKIP_COOLDOWN:{cd_reason}", key))
                        continue

                    q = get_quote(qctx, lp_symbol)
                    # High-price filter for small capital: 1 share cannot exceed a fraction of equity
                    try:
                        last = float(q.last or 0)
                        if last > 0 and last > (equity * max_price_pct_equity):
                            skip_reasons.append((lp_symbol, f"SKIP_HIGH_PRICE:{last:.2f}", key))
                            continue
                        min_price = float(os.environ.get('MIN_PRICE_USD', '5'))
                        if last > 0 and last < min_price:
                            skip_reasons.append((lp_symbol, f"SKIP_LOW_PRICE:{last:.2f}", key))
                            continue
                    except Exception:
                        pass
                    # execution price drift check (signal price vs quote last)
                    try:
                        sig_px = float(s.get('price') or s.get('bar_close') or 0)
                        last = float(q.last or 0)
                        if sig_px > 0 and last > 0:
                            drift = abs(last - sig_px) / sig_px
                            if drift > price_drift_max_pct:
                                skip_reasons.append((lp_symbol, f"SKIP_PRICE_DRIFT:{drift:.3f}", key))
                                continue
                    except Exception:
                        pass

                    intent, reason = try_build_order_intent(
                        s,
                        quote={'last': q.last, 'bid': q.bid, 'ask': q.ask},
                        cfg=PaperTradeConfig(
                        equity=equity,
                        max_sl_pct=float(os.environ.get('MAX_SL_PCT','0.10')),
                        max_position_pct=float(os.environ.get('MAX_POSITION_PCT','0.08')),
                        min_price_usd=float(os.environ.get('MIN_PRICE_USD','5')),
                        min_dollar_vol_20d=float(os.environ.get('MIN_DOLLAR_VOL_20D','20000000')),
                    ),
                    )
                    if not intent:
                        skip_reasons.append((lp_symbol, f"{reason}", key))
                        continue

                    metrics = compute_metrics(intent, signal_score=float(s.get('score') or 0))
                    candidates.append((metrics.score, intent, key))

                candidates.sort(key=lambda x: x[0], reverse=True)

                # SKIP_SUMMARY (debug for dry-run verification)
                try:
                    if skip_reasons:
                        from collections import Counter, defaultdict
                        cnt = Counter([r[1] for r in skip_reasons])
                        print(f"\n[EXEC_SKIP] skipped={len(skip_reasons)} reasons={len(cnt)}")
                        # show top 8 reasons
                        for reason, n in cnt.most_common(8):
                            # show up to 2 sample symbols for this reason
                            samples = [sym for sym, rs, _k in skip_reasons if rs == reason][:2]
                            sample_str = ','.join(samples) if samples else '-'
                            print(f"  - {reason}: {n}  (e.g. {sample_str})")
                except Exception:
                    pass


                if candidates and open_pos_count < max_open_pos:
                    best_score, best_intent, best_key = candidates[0]

                    # portfolio risk cap check (based on known open positions from state)
                    try:
                        new_risk = max(0.0, (float(best_intent.limit_price) - float(best_intent.sl_price)) * float(best_intent.qty))
                    except Exception:
                        new_risk = 0.0
                    if (cur_risk + new_risk) > total_risk_cap_usd:
                        candidates = []

                    # cash buffer guard
                    try:
                        min_cash_buf = float(os.environ.get('MIN_CASH_BUFFER_USD','50'))
                        notional = float(best_intent.limit_price or 0) * float(best_intent.qty or 0)
                        if (equity - notional) < min_cash_buf:
                            candidates = []
                            skip_reasons.append((best_intent.symbol, f"SKIP_CASH_BUFFER:{min_cash_buf}", best_key))
                    except Exception:
                        pass

                    # Record paper ledger (always) for audit
                    if os.environ.get('PAPER_TRADING', 'on') == 'on':
                        append_ledger(best_intent, fill_price=best_intent.limit_price, status='FILLED')
                        print(f"\nPAPER_ORDER:{best_intent.symbol}:{best_intent.side}:{best_intent.qty}@{best_intent.limit_price}")

                    # Live submit path (hard-gated). Default is dry-run.
                    if is_live() and live_trading_enabled():
                        from broker.live_executor import submit_live_order
                        dry_run = (os.environ.get('LIVE_SUBMIT', '0') != '1')
                        r = submit_live_order(best_intent, dry_run=dry_run)
                        if r.ok and r.dry_run:
                            print(f"\nLIVE_ORDER_DRYRUN:{best_intent.symbol}:{best_intent.side}:{best_intent.qty}@{best_intent.limit_price}")
                        elif r.ok:
                            print(f"\nLIVE_ORDER_OK:{best_intent.symbol}:order_id={r.order_id}")
                        else:
                            print(f"\nLIVE_ORDER_FAIL:{best_intent.symbol}:{r.error}")

                    mark_executed(best_key, meta={'symbol': best_intent.symbol, 'qty': best_intent.qty})
                    try:
                        add_open_position(best_intent.symbol, best_intent.qty, float(best_intent.limit_price or 0), best_intent.sl_price, best_intent.tp_price, meta={'key': best_key})
                    except Exception:
                        pass
                    inc_daily(day_key)

        except Exception as _e:
            print(f"  [execution-select failed] {_e}")

    # --- 2) Send normal as one batch (top list)
    if normal_buy:
        lines = [
            f"📦 普通信号汇总（{datetime.now().strftime('%Y-%m-%d %H:%M')} 北京）",
            f"共 {len(normal_buy)} 只（已去重/已过滤）",
            "",
        ]
        # keep short: show up to 10
        for s in sorted(normal_buy, key=lambda x: float(x.get('score',0) or 0), reverse=True)[:10]:
            mode = s.get('exec_mode','-')
            reason = s.get('exec_reason','-')

            # proximity hints (for quick operator reading)
            try:
                bb = float(s.get('bb_pct', 0.5) or 0.5)
            except Exception:
                bb = 0.5
            try:
                atr = float(s.get('atr_pct14', 999) or 999)
            except Exception:
                atr = 999
            ma200 = bool(s.get('above_ma200', False))
            st = s.get('structure') or {}
            has_struct = bool((st.get('signals') or []))

            mr_gap = max(0.0, bb - 0.10)
            struct_gaps = []
            if not has_struct: struct_gaps.append('缺结构')
            if not ma200: struct_gaps.append('MA200❌')
            if atr > ATR_PCT14_MAX: struct_gaps.append(f"ATR%>{ATR_PCT14_MAX}")
            struct_hint = ' / '.join(struct_gaps) if struct_gaps else 'OK'

            hint = f"MR距触发BB={bb:.2f}(差{mr_gap:.2f})｜STRUCT:{struct_hint}"

            # persist hint fields for tracking
            s['mr_bb_gap'] = round(mr_gap, 3)
            s['struct_hint'] = struct_hint

            lines.append(f"• {s['ticker']}｜{mode}｜score {s.get('score')}｜${s.get('price')}｜{hint}")
        lines.append("\n（提示：强信号/STRUCT 会单独推送）")
        batch_msg = "\n".join(lines)

        print(f"\nBUY_SIGNAL_BATCH:{len(normal_buy)}")
        print(batch_msg)
        print("---END---")
        output_lines.append(f"BUY_SIGNAL_BATCH:{len(normal_buy)}")
        output_lines.append(batch_msg)
        output_lines.append("---END---")

    # --- 3) Always save signals to Dashboard for all new buys
    for sig in new_buy:
        # 自动保存到 Dashboard signals.json
        try:
            import sys as _sys
            _sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../dashboard'))
            from export_signals import add_buy_signal
            add_buy_signal(sig)
        except Exception as _e:
            print(f"  [Dashboard 同步失败] {_e}")

    # --- 4) push_history: strong singles + one batch record
    for sig in strong_buy:
        try:
            import sys as _sys
            _sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../dashboard'))
            from export_push_history import append_push_history
            msg = format_signal_message(sig)
            level = '🔥 强烈信号' if sig.get('score',0) >= 85 else ('🧱 STRUCT' if sig.get('exec_mode')=='STRUCT' else '✅ 买入信号')
            title = f"买入信号 {sig['ticker']} ({level})"
            summary = f"{sig['ticker']} {level}｜评分{sig.get('score')}｜触发1H收盘价 ${sig.get('price')}"
            append_push_history(
                type_='buy_signal',
                title=title,
                summary=summary,
                raw=msg,
                time=sig.get('scan_time'),
                meta={
                    'ticker': sig.get('ticker'),
                    'score': sig.get('score'),
                    'level': level,
                    'bar_time': sig.get('bar_time'),
                    'bar_close': sig.get('bar_close'),
                    'price_source': sig.get('price_source','1H_bar_close'),
                    'exec_mode': sig.get('exec_mode'),
                    'exec_reason': sig.get('exec_reason'),
                }
            )
        except Exception as _e:
            print(f"  [push_history 单条同步失败] {_e}")

    if new_buy:
        try:
            import sys as _sys
            _sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../dashboard'))
            from export_push_history import append_push_history
            append_push_history(
                type_='buy_signal_batch',
                title=batch_title,
                summary=batch_summary,
                raw=batch_raw,
                time=datetime.now().strftime('%Y-%m-%d %H:%M'),
                signal_count=len(new_buy),
                strong_count=len(strong_buy),
            )
        except Exception as _e:
            print(f"  [推送历史同步失败] {_e}")

    save_state(state)

    # ════════════════════════════════════
    # 输出汇总
    # ════════════════════════════════════
    total_alerts = len(exit_alerts) + len(new_buy) if portfolio else len(new_buy)
    if total_alerts == 0:
        print("\nNO_SIGNAL")
        state['no_signal_streak'] = int(state.get('no_signal_streak', 0) or 0) + 1
    else:
        print(f"\n共触发 {total_alerts} 个提醒（卖出:{len(exit_alerts) if portfolio else 0} 买入:{len(new_buy)}）")
        state['no_signal_streak'] = 0

    # ════════════════════════════════════
    # 盘中：每次扫描后更新持仓诊断 + 自动 push
    # ════════════════════════════════════
    try:
        import sys as _sys
        _sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../jobs'))
        from portfolio_diagnosis import run as run_diagnosis
        print("\n[持仓诊断] 盘中自动更新...")
        run_diagnosis()
    except Exception as _e:
        print(f"  [持仓诊断更新失败] {_e}")


if __name__ == '__main__':
    main()
