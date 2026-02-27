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

    # ════════════════════════════════════
    # 第一部分：检查持仓止盈止损
    # ════════════════════════════════════
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
            lines.append(f"• {s['ticker']}｜{mode}｜score {s.get('score')}｜${s.get('price')}｜{reason}")
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
