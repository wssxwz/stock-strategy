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
        f"🌙 **盘后复盘（执行版）** | {date_str}",
        "━━━━━━━━━━━━━━━━",
    ]

    # 1) Tape read
    lines.append("\n📌 **今晚主线（1句话）**")
    spy = idx.get('^GSPC',{}).get('change_pct',0)
    qqq = idx.get('^NDX',{}).get('change_pct',0)
    dia = idx.get('^DJI',{}).get('change_pct',0)
    lines.append(f"  标普{fmt(spy)}｜纳指{fmt(qqq)}｜道指{fmt(dia)}｜{fg['emoji']} {fg['label_zh']} {fg['value']}")

    # 2) What changed for portfolio
    lines.append("\n💼 **持仓：今晚需要知道的3件事**")
    if pnl_list:
        winners = [p for p in pnl_list if p['ret_pct']>=0][:3]
        losers  = [p for p in pnl_list if p['ret_pct']<0][-3:]
        if winners:
            lines.append("  • 强势：" + '，'.join([f"{p['ticker']} {fmt(p['ret_pct'])}" for p in winners]))
        if losers:
            lines.append("  • 承压：" + '，'.join([f"{p['ticker']} {fmt(p['ret_pct'])}" for p in losers]))
        total_ret = sum(p['ret_pct'] for p in pnl_list) / len(pnl_list)
        lines.append(f"  • 组合均值：{fmt(total_ret)}（只看方向，不做精确净值）")
    else:
        lines.append("  • 未检测到持仓记录（portfolio.json 为空）")

    # 3) Tomorrow focus
    lines.append("\n🎯 **明天开盘前要盯什么**")
    if sects:
        sl = list(sects.items())
        lines.append(f"  • 板块：最强 {sl[0][1]['name']} {fmt(sl[0][1]['change_pct'])}｜最弱 {sl[-1][1]['name']} {fmt(sl[-1][1]['change_pct'])}")
    if tomorrow_events:
        lines.append("  • 事件：" + '；'.join(tomorrow_events[:3]))
    lines.append("  • 节奏：21:00 盘前前瞻｜盘中按小时扫描｜回撤到 MR/结构条件再出手")

    # Signals summary (short)
    lines.append("\n📡 **今日信号（简）**")
    if signals:
        lines.append('  ' + '，'.join([f"{s['ticker']}({s['score']})" for s in signals[:8]]))
    else:
        lines.append("  无触发")

    lines.append("\n━━━━━━━━━━━━━━━━")
    lines.append("_仅供参考_")

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
