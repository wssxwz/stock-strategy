"""
单次扫描 + 直接通过 OpenClaw 发送 Telegram 通知
这个脚本由 OpenClaw cron 定时调用
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../src'))

from signal_engine import run_scan, format_signal_message
from config import WATCHLIST, NOTIFY
from datetime import datetime

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

if __name__ == '__main__':
    if not WATCHLIST:
        print("WATCHLIST 为空")
        sys.exit(0)

    state = load_state()
    signals = run_scan(WATCHLIST)

    new_signals = []
    for sig in signals:
        key = signal_key(sig)
        if key not in state['sent_signals']:
            new_signals.append(sig)
            state['sent_signals'][key] = {
                'ticker': sig['ticker'], 'score': sig['score'],
                'price': sig['price'], 'time': datetime.now().isoformat()
            }

    # 输出到 stdout（OpenClaw 捕获后发送）
    if new_signals:
        for sig in new_signals:
            msg = format_signal_message(sig)
            print(f"SIGNAL:{sig['ticker']}:{sig['score']}")
            print(msg)
            print("---END---")
    else:
        print("NO_SIGNAL")

    save_state(state)
