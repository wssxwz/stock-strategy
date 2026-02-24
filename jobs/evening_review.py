"""
收盘复盘 Job - 每天 21:00 UTC (北京时间 05:00, 收盘后)
复盘今日，预告明日
"""
import sys, os, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from market_data import (
    get_batch_quotes, get_fear_greed, get_sector_performance,
    INDICES, save_daily_data, load_daily_data
)
from datetime import datetime, timedelta
import json


def load_today_signals() -> list:
    """加载今日触发的信号"""
    state_path = os.path.join(os.path.dirname(__file__), '../monitor/.monitor_state.json')
    if not os.path.exists(state_path):
        return []
    with open(state_path) as f:
        state = json.load(f)
    today = datetime.now().strftime('%Y-%m-%d')
    return [
        v for k, v in state.get('sent_signals', {}).items()
        if today in k
    ]


def load_portfolio() -> dict:
    """加载持仓"""
    path = os.path.join(os.path.dirname(__file__), '../monitor/portfolio.json')
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def get_portfolio_pnl(portfolio: dict) -> list:
    """计算持仓盈亏"""
    if not portfolio:
        return []
    tickers = list(portfolio.keys())
    quotes  = get_batch_quotes(tickers)
    results = []
    for ticker, pos in portfolio.items():
        if pos.get('closed'):
            continue
        current = quotes.get(ticker, {}).get('price', pos['entry_price'])
        ret = (current - pos['entry_price']) / pos['entry_price'] * 100
        results.append({
            'ticker':    ticker,
            'entry':     pos['entry_price'],
            'current':   current,
            'ret_pct':   round(ret, 2),
            'tp':        pos['take_profit'],
            'sl':        pos['stop_loss'],
        })
    return sorted(results, key=lambda x: x['ret_pct'], reverse=True)


def get_tomorrow_preview() -> list:
    """获取明日重要事件（简单版：大市值财报）"""
    import yfinance as yf
    events = []
    big_caps = ['NVDA','AAPL','MSFT','AMZN','META','GOOGL','TSLA','AVGO']
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

    for ticker in big_caps:
        try:
            t = yf.Ticker(ticker)
            cal = t.calendar
            if cal is not None and not cal.empty and 'Earnings Date' in cal.index:
                dates = cal.loc['Earnings Date']
                for d in (dates if hasattr(dates, '__iter__') else [dates]):
                    if str(d)[:10] == tomorrow:
                        events.append(f"💼 {ticker} 财报公布")
                        break
        except:
            pass

    return events


def generate_evening_review() -> str:
    now = datetime.now()
    date_str = now.strftime('%Y年%m月%d日')

    # 收盘行情
    idx    = get_batch_quotes(list(INDICES.keys()))
    fg     = get_fear_greed()
    sects  = get_sector_performance()

    # 今日信号
    signals = load_today_signals()

    # 持仓盈亏
    portfolio = load_portfolio()
    pnl_list  = get_portfolio_pnl(portfolio)

    # 明日预告
    tomorrow_events = get_tomorrow_preview()

    def fmt(pct): return f"{'+'if pct>=0 else ''}{pct:.2f}%"
    def arr(pct): return '🔺' if pct > 0 else '🔻'

    lines = [
        f"🌙 **收盘复盘** | {date_str}",
        "━━━━━━━━━━━━━━━━",
    ]

    # 今日收盘
    lines.append("\n📊 **今日收盘**")
    for t, name in [('SPY','标普500'),('QQQ','纳斯达克'),('DIA','道指')]:
        if t in idx:
            lines.append(f"  {arr(idx[t]['change_pct'])} {name}  {fmt(idx[t]['change_pct'])}")
    lines.append(f"  {fg['emoji']} 情绪：{fg['label_zh']}（指数 {fg['value']}，0=极恐 100=极贪）")

    # 今日信号回顾
    if signals:
        lines.append(f"\n📡 **今日触发信号 ({len(signals)}个)**")
        for s in signals[:5]:
            lines.append(f"  🎯 {s['ticker']} | 评分:{s['score']} | ${s['price']}")
    else:
        lines.append("\n📡 **今日信号：** 无触发")

    # 持仓盈亏
    if pnl_list:
        lines.append(f"\n💼 **持仓状况 ({len(pnl_list)}只)**")
        total_ret = sum(p['ret_pct'] for p in pnl_list) / len(pnl_list)
        for p in pnl_list:
            emoji = '🟢' if p['ret_pct'] >= 0 else '🔴'
            lines.append(f"  {emoji} {p['ticker']}  {fmt(p['ret_pct'])}  (入场${p['entry']} → 现${p['current']})")
        lines.append(f"  📈 平均浮盈：{fmt(total_ret)}")
    else:
        lines.append("\n💼 **持仓：** 暂无记录")

    # 最强/最弱板块
    if sects:
        sl = list(sects.items())
        lines.append(f"\n🏆 最强：{sl[0][1]['name']} {fmt(sl[0][1]['change_pct'])}  |  最弱：{sl[-1][1]['name']} {fmt(sl[-1][1]['change_pct'])}")

    # 明日预告
    lines.append("\n📅 **明日关注**")
    if tomorrow_events:
        for e in tomorrow_events:
            lines.append(f"  {e}")
    lines.append("  → 早盘摘要 7:50 推送")

    lines.append("\n━━━━━━━━━━━━━━━━")
    lines.append("_仅供参考，祝好梦！🌙_")

    msg = '\n'.join(lines)

    # 保存
    save_daily_data({
        'evening_review': {
            'generated_at':   now.isoformat(),
            'signals_count':  len(signals),
            'positions_count':len(pnl_list),
        }
    })

    return msg


if __name__ == '__main__':
    print("生成收盘复盘...")
    msg = generate_evening_review()
    print("\nEVENING_REVIEW_START")
    print(msg)
    print("EVENING_REVIEW_END")
