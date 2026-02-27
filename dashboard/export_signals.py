"""
信号导出工具 - 供 cron 调用，自动保存推送记录到 Dashboard
"""
import json, os, sys
from datetime import datetime

SIGNALS_FILE = os.path.join(os.path.dirname(__file__), 'signals.json')
REPORTS_DIR = os.path.join(os.path.dirname(__file__), 'reports')

def load_signals():
    if os.path.exists(SIGNALS_FILE):
        with open(SIGNALS_FILE) as f:
            return json.load(f)
    return []

def save_signals(signals):
    with open(SIGNALS_FILE, 'w') as f:
        json.dump(signals, f, indent=2, default=str)

def add_buy_signal(sig: dict) -> bool:
    """
    添加买入信号
    sig 格式来自 monitor/signal_engine.py 的 score_signal 返回值
    """
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
            'schema_version': 2,
            'type': 'buy',
            'ticker': sig['ticker'],
            'score': sig['score'],
            'kb_tag': sig.get('kb_tag', ''),
            'price': sig.get('bar_close', sig.get('price')),
            'price_source': sig.get('price_source', '1H_bar_close'),
            'bar_time': sig.get('bar_time'),
            'bar_close': sig.get('bar_close', sig.get('price')),
            'suggest_price': sig.get('suggest_price'),
            'suggest_note': sig.get('suggest_note', ''),
            # key indicators for later analysis
            'rsi14': sig.get('rsi14', None),
            'bb_pct': sig.get('bb_pct', None),
            'macd_hist': sig.get('macd_hist', None),
            'vol_ratio': sig.get('vol_ratio', None),
            'ret_5d': sig.get('ret_5d', None),
            'above_ma200': sig.get('above_ma200', None),
            'above_ma50': sig.get('above_ma50', None),
            'risk_mode': sig.get('risk_mode', None),
            'rs_1y': sig.get('rs_1y', None),
            # exits
            'tp_price': sig.get('tp_price', 0),
            'sl_price': sig.get('sl_price', 0),
            'rr_ratio': sig.get('rr_ratio', None),
            'time': sig.get('scan_time', datetime.now().strftime('%Y-%m-%d %H:%M')),
            'archived': False,
            'position_taken': False
        })
        save_signals(signals)
        print(f"  ✅ 已保存信号：{sig['ticker']} (评分：{sig['score']})")
        return True
    else:
        print(f"  ⏭️  跳过重复信号：{sig['ticker']}")
        return False

def save_morning_brief(msg: str):
    """保存早盘摘要"""
    date_str = datetime.now().strftime('%Y-%m-%d')
    path = os.path.join(REPORTS_DIR, f'morning_{date_str}.json')
    os.makedirs(REPORTS_DIR, exist_ok=True)
    with open(path, 'w') as f:
        json.dump({
            'type': 'morning_brief',
            'date': date_str,
            'generated_at': datetime.now().isoformat(),
            'content': msg
        }, f, indent=2, default=str)
    print(f"  ✅ 已保存早盘摘要")

def save_deep_analysis(msg: str, html_path: str):
    """保存深度早报"""
    date_str = datetime.now().strftime('%Y-%m-%d')
    path = os.path.join(REPORTS_DIR, f'deep_{date_str}.json')
    with open(path, 'w') as f:
        json.dump({
            'type': 'deep_analysis',
            'date': date_str,
            'generated_at': datetime.now().isoformat(),
            'telegram_msg': msg,
            'html_report': html_path
        }, f, indent=2, default=str)
    print(f"  ✅ 已保存深度早报")

def save_evening_review(msg: str):
    """保存收盘复盘"""
    date_str = datetime.now().strftime('%Y-%m-%d')
    path = os.path.join(REPORTS_DIR, f'evening_{date_str}.json')
    with open(path, 'w') as f:
        json.dump({
            'type': 'evening_review',
            'date': date_str,
            'generated_at': datetime.now().isoformat(),
            'content': msg
        }, f, indent=2, default=str)
    print(f"  ✅ 已保存收盘复盘")

def export_from_scan_output():
    """从标准输入解析扫描输出，提取信号并保存"""
    current_signal = None
    buy_count = 0
    
    for line in sys.stdin:
        line = line.strip()
        
        # 检测 BUY_SIGNAL 开始
        if line.startswith('BUY_SIGNAL:'):
            parts = line.split(':')
            ticker = parts[1] if len(parts) > 1 else ''
            score = int(parts[2]) if len(parts) > 2 else 0
            current_signal = {'ticker': ticker, 'score': score}
        
        # 检测信号结束，保存
        elif line == '---END---' and current_signal:
            if add_buy_signal(current_signal):
                buy_count += 1
            current_signal = None
    
    print(f"\n共保存 {buy_count} 个新信号到 Dashboard")

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
        add_buy_signal(test_sig)
        print(f"当前信号总数：{len(load_signals())}")
