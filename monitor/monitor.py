"""
监控主程序
每小时在美股交易时段自动扫描，触发信号时通过 OpenClaw 发送 Telegram 通知
运行方式: python monitor.py
"""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../src'))

from datetime import datetime, timedelta
import pytz
from signal_engine import run_scan, format_signal_message
from config import WATCHLIST, STRATEGY, NOTIFY

# 状态文件（避免重复发送）
STATE_FILE = os.path.join(os.path.dirname(__file__), '.monitor_state.json')

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {'sent_signals': {}, 'last_scan': None}

def save_state(state: dict):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def is_market_hours() -> bool:
    """判断当前是否在美股交易时段（北京时间）"""
    now_bj = datetime.now(pytz.timezone('Asia/Shanghai'))
    hour = now_bj.hour
    minute = now_bj.minute

    # 北京时间 21:30 ~ 次日 04:00（夏令时 20:30~03:00）
    # 简化处理：21:00~04:30 都允许扫描
    in_session = (hour >= 21) or (hour < 5)
    return in_session

def signal_key(sig: dict) -> str:
    """信号去重 key：同一股票同一评分区间当天只发一次"""
    date_str = datetime.now().strftime('%Y-%m-%d')
    score_tier = sig['score'] // 10 * 10  # 按10分段去重
    return f"{sig['ticker']}_{date_str}_{score_tier}"

def send_telegram(message: str):
    """通过 OpenClaw message 工具发送 Telegram"""
    # 写入文件，由外部调用
    msg_file = '/tmp/stock_signal_msg.txt'
    with open(msg_file, 'w') as f:
        f.write(message)
    # 通过 openclaw CLI 发送
    os.system(f'openclaw message send --channel telegram --message-file {msg_file} 2>/dev/null')

def main():
    print("=" * 60)
    print(f"🤖 股票监控系统启动")
    print(f"   股票池: {len(WATCHLIST)} 只")
    print(f"   扫描间隔: {STRATEGY['scan_interval_min']} 分钟")
    print(f"   交易时段: 北京 21:00~04:30")
    print(f"   触发阈值: 评分 ≥ {NOTIFY['min_score']} 发通知")
    print("=" * 60)

    if not WATCHLIST:
        print("\n⚠️  WATCHLIST 为空！请先在 config.py 中添加股票列表")
        return

    state = load_state()
    scan_interval = STRATEGY['scan_interval_min'] * 60  # 转秒

    while True:
        now = datetime.now()

        if not is_market_hours():
            next_open = now.replace(hour=21, minute=30, second=0)
            if now.hour >= 5:
                next_open = next_open
            wait_sec = (next_open - now).total_seconds()
            if wait_sec < 0:
                wait_sec += 86400
            print(f"\n[{now.strftime('%H:%M')}] 非交易时段，等待开市... (约{wait_sec/3600:.1f}小时后)")
            time.sleep(min(wait_sec, 1800))  # 最多等30分钟再检查
            continue

        # 执行扫描
        print(f"\n[{now.strftime('%Y-%m-%d %H:%M')}] 开始扫描...")
        try:
            signals = run_scan(WATCHLIST)
            state['last_scan'] = now.isoformat()

            for sig in signals:
                key = signal_key(sig)
                if key in state['sent_signals']:
                    print(f"  跳过 {sig['ticker']}（今日已发过相同信号）")
                    continue

                # 格式化并发送
                msg = format_signal_message(sig)
                print(f"\n📨 发送信号: {sig['ticker']} (评分{sig['score']})")

                # 记录已发送
                state['sent_signals'][key] = {
                    'ticker': sig['ticker'],
                    'score':  sig['score'],
                    'price':  sig['price'],
                    'time':   now.isoformat(),
                }

                # 输出信号内容（供 OpenClaw 读取并发送）
                print("\n" + "─"*50)
                print(msg)
                print("─"*50)

            save_state(state)

        except Exception as e:
            print(f"  ✗ 扫描出错: {e}")

        # 等待下次扫描
        print(f"\n  下次扫描: {(now + timedelta(seconds=scan_interval)).strftime('%H:%M')}")
        time.sleep(scan_interval)


if __name__ == '__main__':
    main()
