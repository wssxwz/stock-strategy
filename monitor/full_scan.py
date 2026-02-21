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
    # 第二部分：扫描买入信号
    # ════════════════════════════════════
    print(f"\n[买入扫描] 开始扫描 {len(WATCHLIST)} 只股票...")
    candidates = phase1_filter(WATCHLIST)
    buy_signals = phase2_score(candidates) if candidates else []

    new_buy = []
    for sig in buy_signals:
        key = signal_key(sig)
        if key not in state['sent_signals']:
            new_buy.append(sig)
            state['sent_signals'][key] = {
                'ticker': sig['ticker'], 'score': sig['score'],
                'price': sig['price'], 'time': datetime.now().isoformat()
            }

    for sig in new_buy:
        msg = format_signal_message(sig)
        print(f"\nBUY_SIGNAL:{sig['ticker']}:{sig['score']}")
        print(msg)
        print("---END---")
        output_lines.append(f"BUY_SIGNAL:{sig['ticker']}:{sig['score']}")
        output_lines.append(msg)
        output_lines.append("---END---")

    save_state(state)

    # ════════════════════════════════════
    # 输出汇总
    # ════════════════════════════════════
    total_alerts = len(exit_alerts) + len(new_buy) if portfolio else len(new_buy)
    if total_alerts == 0:
        print("\nNO_SIGNAL")
    else:
        print(f"\n共触发 {total_alerts} 个提醒（卖出:{len(exit_alerts) if portfolio else 0} 买入:{len(new_buy)}）")


if __name__ == '__main__':
    main()
