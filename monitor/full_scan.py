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
from fast_scan import phase1_filter, phase2_score
from portfolio import load_portfolio, check_positions, format_exit_alert
from signal_engine import format_signal_message
from config import WATCHLIST, NOTIFY
from market_regime import get_market_regime, regime_header, get_score_threshold

STATE_FILE = os.path.join(os.path.dirname(__file__), '.monitor_state.json')

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {'sent_signals': {}}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2, default=str)

def signal_key(sig):
    date_str = datetime.now().strftime('%Y-%m-%d')
    return f"{sig['ticker']}_{date_str}_{sig['score']//10*10}"

def get_current_prices(tickers: list) -> dict:
    """批量获取当前价格"""
    prices = {}
    if not tickers:
        return prices
    try:
        data = yf.download(tickers, period='1d', interval='1m',
                           auto_adjust=True, progress=False, threads=True)
        if len(tickers) == 1:
            prices[tickers[0]] = float(data['Close'].iloc[-1])
        else:
            for t in tickers:
                try:
                    prices[t] = float(data['Close'][t].iloc[-1])
                except:
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
    print(f"\n[买入扫描] 开始扫描 {len(WATCHLIST)} 只股票...")
    candidates = phase1_filter(WATCHLIST)
    # phase2_score 后按动态阈值过滤（P3：按股票类型细化阈值）
    buy_signals_raw = phase2_score(candidates) if candidates else []
    buy_signals = []
    for s in buy_signals_raw:
        ticker_threshold = get_score_threshold(s['ticker'], regime)
        s['score_threshold'] = ticker_threshold  # 记录该股实际阈值
        if s['score'] >= ticker_threshold:
            buy_signals.append(s)
    print(f"[信号过滤] 原始触发 {len(buy_signals_raw)} 只 → 达到阈值 {len(buy_signals)} 只")

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

    # 批量推送历史写入（一次扫描=1 条批次记录）
    batch_raw = "\n\n".join([format_signal_message(sig) for sig in new_buy])
    if new_buy:
        batch_title = f"📣 全市场扫描信号（{datetime.now().strftime('%Y-%m-%d %H:%M')} 北京）"
        batch_summary = f"✅ 买入 {len(new_buy)} / 卖出 0｜强趋势 {sum(1 for s in new_buy if s['score']>=85)} 只｜{regime['regime_zh']}模式"
    
    for sig in new_buy:
        msg = format_signal_message(sig)
        print(f"\nBUY_SIGNAL:{sig['ticker']}:{sig['score']}")
        print(msg)
        print("---END---")
        output_lines.append(f"BUY_SIGNAL:{sig['ticker']}:{sig['score']}")
        output_lines.append(msg)
        output_lines.append("---END---")

        # 自动保存到 Dashboard signals.json
        try:
            import sys as _sys
            _sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../dashboard'))
            from export_signals import add_buy_signal
            add_buy_signal(sig)
        except Exception as _e:
            print(f"  [Dashboard 同步失败] {_e}")

        # 单条信号写入 push_history（保持与 Telegram 原文一致）
        try:
            import sys as _sys
            _sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../dashboard'))
            from export_push_history import append_push_history

            level = '🔥 强烈信号' if sig.get('score',0) >= 85 else '✅ 买入信号'
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
                }
            )
        except Exception as _e:
            print(f"  [push_history 单条同步失败] {_e}")
    
    # 整批写入 push_history（1 条记录）
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
                strong_count=sum(1 for s in new_buy if s['score']>=85),
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
    else:
        print(f"\n共触发 {total_alerts} 个提醒（卖出:{len(exit_alerts) if portfolio else 0} 买入:{len(new_buy)}）")

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
