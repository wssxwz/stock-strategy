"""
信号导出工具
将监控器扫描到的信号导出为 JSON，供 Dashboard 导入
"""
import json, os, sys
from datetime import datetime

SIGNALS_FILE = os.path.join(os.path.dirname(__file__), 'signals.json')

def load_signals():
    if os.path.exists(SIGNALS_FILE):
        with open(SIGNALS_FILE) as f:
            return json.load(f)
    return []

def save_signals(signals):
    with open(SIGNALS_FILE, 'w') as f:
        json.dump(signals, f, indent=2, default=str)

def add_signal(sig: dict):
    """添加一个新信号"""
    signals = load_signals()
    
    # 去重（同一天同一股票同一评分段）
    date_str = datetime.now().strftime('%Y-%m-%d')
    key = f"{sig['ticker']}_{date_str}_{sig['score']//10*10}"
    
    exists = any(
        s.get('ticker') == sig['ticker'] and
        s.get('time', '').startswith(date_str) and
        s.get('score', 0)//10*10 == sig['score']//10*10
        for s in signals
    )
    
    if not exists:
        signals.insert(0, {
            'id': f"sig_{datetime.now().timestamp()}",
            'type': 'buy',
            'ticker': sig['ticker'],
            'score': sig['score'],
            'price': sig['price'],
            'suggest_price': sig.get('suggest_price'),
            'rsi14': sig.get('rsi14', 0),
            'bb_pct': sig.get('bb_pct', 0),
            'tp_price': sig.get('tp_price', 0),
            'sl_price': sig.get('sl_price', 0),
            'time': sig.get('scan_time', datetime.now().strftime('%Y-%m-%d %H:%M')),
            'archived': False,
            'position_taken': False
        })
        save_signals(signals)
        print(f"✅ 已添加信号：{sig['ticker']} (评分：{sig['score']})")
        return True
    else:
        print(f"⏭️  跳过重复信号：{sig['ticker']}")
        return False

def export_from_scan_output():
    """从标准输入解析扫描输出，提取信号"""
    for line in sys.stdin:
        line = line.strip()
        if line.startswith('BUY_SIGNAL:'):
            parts = line.split(':')
            ticker = parts[1]
            score = int(parts[2]) if len(parts) > 2 else 0
            add_signal({'ticker': ticker, 'score': score})

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--stdin':
        export_from_scan_output()
    else:
        # 测试模式
        test_sig = {
            'ticker': 'TEST',
            'score': 75,
            'price': 100.5,
            'suggest_price': 99.5,
            'rsi14': 32.5,
            'bb_pct': 0.15,
            'tp_price': 113.5,
            'sl_price': 92.5,
            'scan_time': datetime.now().strftime('%Y-%m-%d %H:%M')
        }
        add_signal(test_sig)
        print(f"当前信号总数：{len(load_signals())}")
