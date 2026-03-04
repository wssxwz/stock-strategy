"""
周末市场总结 Job
每周一 7:30 北京时间 (UTC 23:30 周日) 运行
抓取周末新闻 + 生成结构化周报 → 保存到 Dashboard + Telegram 推送
"""
import sys, os, json, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from market_data import get_batch_quotes, get_fear_greed, get_sector_performance, INDICES, save_daily_data
from datetime import datetime, timedelta
import urllib.request

DASHBOARD_DIR = os.path.join(os.path.dirname(__file__), '../dashboard')
WEEKLY_FILE   = os.path.join(DASHBOARD_DIR, 'weekly_reports.json')


def load_reports():
    if os.path.exists(WEEKLY_FILE):
        with open(WEEKLY_FILE) as f:
            return json.load(f)
    return []


def save_reports(reports):
    with open(WEEKLY_FILE, 'w') as f:
        json.dump(reports, f, indent=2, default=str)


def fetch_news_headlines() -> list:
    """从 Yahoo Finance RSS 获取最新财经新闻"""
    headlines = []
    try:
        url = 'https://finance.yahoo.com/news/rssindex'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read().decode('utf-8')
        import re
        titles = re.findall(r'<title><!\[CDATA\[(.*?)\]\]></title>', content)
        descs  = re.findall(r'<description><!\[CDATA\[(.*?)\]\]></description>', content)
        for t, d in zip(titles[1:16], descs[1:16]):  # 跳过第一个（频道标题）
            headlines.append({'title': t.strip(), 'desc': d.strip()[:120]})
    except Exception as e:
        print(f"  新闻获取失败: {e}")
    return headlines


def analyze_headlines(headlines: list, market_data: dict) -> dict:
    """
    基于新闻标题 + 市场数据，生成结构化周报
    规则引擎（后续可升级为 AI）
    """
    # 关键词分类
    tariff_kw  = ['tariff','trade','tariffs','customs','import']
    ai_kw      = ['ai','nvidia','artificial intelligence','chips','semiconductor']
    fed_kw     = ['fed','federal reserve','interest rate','inflation','cpi','fomc']
    geo_kw     = ['iran','russia','ukraine','china','war','military','geopolit']
    tech_kw    = ['apple','google','meta','microsoft','amazon','tech']

    events = []
    all_text = ' '.join(h['title'].lower() + ' ' + h['desc'].lower() for h in headlines)

    # 关税事件
    tariff_news = [h for h in headlines if any(k in h['title'].lower() for k in tariff_kw)]
    if tariff_news:
        events.append({
            'emoji': '🏛️',
            'title': '关税政策动态',
            'detail': tariff_news[0]['title'],
            'impact': '❌ 利空 — 贸易不确定性上升',
            'impact_class': 'bearish'
        })

    # AI/芯片
    ai_news = [h for h in headlines if any(k in h['title'].lower() for k in ai_kw)]
    if ai_news:
        events.append({
            'emoji': '🤖',
            'title': 'AI / 芯片板块',
            'detail': ai_news[0]['title'],
            'impact': '✅ 关注 — NVDA 财报周',
            'impact_class': 'bullish'
        })

    # 美联储/经济数据
    fed_news = [h for h in headlines if any(k in h['title'].lower() for k in fed_kw)]
    if fed_news:
        events.append({
            'emoji': '🏦',
            'title': '美联储 / 宏观数据',
            'detail': fed_news[0]['title'],
            'impact': '⚠️ 关注 — 影响降息预期',
            'impact_class': 'neutral'
        })

    # 地缘政治
    geo_news = [h for h in headlines if any(k in h['title'].lower() for k in geo_kw)]
    if geo_news:
        events.append({
            'emoji': '🌍',
            'title': '地缘政治',
            'detail': geo_news[0]['title'],
            'impact': '⚠️ 注意 — 影响能源/国防板块',
            'impact_class': 'warning'
        })

    # 如果新闻少，补充一个默认条目
    if not events:
        for h in headlines[:3]:
            events.append({
                'emoji': '📰',
                'title': h['title'][:40],
                'detail': h['desc'],
                'impact': '关注中',
                'impact_class': 'neutral'
            })

    # 市场方向判断
    sp500 = market_data.get('indices', {}).get('^GSPC', {}).get('change_pct', 0)
    fg    = market_data.get('fear_greed', {}).get('value', 50)
    tariff_bear = len(tariff_news) > 0

    if sp500 > 0.5 and not tariff_bear:
        mood, mood_emoji, mood_class = '多头偏强', '🟢', 'bullish'
    elif sp500 < -0.5 or tariff_bear:
        mood, mood_emoji, mood_class = '谨慎偏空', '🔴', 'bearish'
    else:
        mood, mood_emoji, mood_class = '震荡观望', '🟡', 'neutral'

    # 今晚开盘预判
    outlook_items = []
    if tariff_bear:
        outlook_items.append('⚠️ 关税不确定性压制情绪，预计小幅低开，后续走势取决于白宫表态')
    if fg < 30:
        outlook_items.append(f'😱 市场情绪极度恐惧（{fg}/100），历史上往往是中期低点，可关注超跌买入机会')
    elif fg > 70:
        outlook_items.append(f'🤑 市场情绪极度贪婪（{fg}/100），注意高位风险，控制仓位')
    if ai_news:
        outlook_items.append('🔥 NVDA 财报本周发布，AI板块情绪主导，关注指引和数据中心订单')
    if not outlook_items:
        outlook_items.append('📊 市场等待明确催化剂，操作以跟随信号为主')

    # 核心持仓判断
    core_stocks = [
        {'ticker': 'NVDA', 'outlook': '🔥 重点关注', 'outlook_class': 'bullish',
         'reason': '本周财报，AI叙事核心，波动大，财报前不追高'},
        {'ticker': 'GOOGL', 'outlook': '😐 中性持有', 'outlook_class': 'neutral',
         'reason': '关税对广告间接影响，随大盘走，可持有'},
        {'ticker': 'META',  'outlook': '😐 中性持有', 'outlook_class': 'neutral',
         'reason': 'AI资本开支叙事支撑，持有为主'},
        {'ticker': 'TSLA',  'outlook': '⚠️ 谨慎观望', 'outlook_class': 'bearish' if tariff_bear else 'neutral',
         'reason': '关税影响供应链，等待技术信号再入场'},
    ]

    # 本周策略
    strategy = [
        '📌 周一：观望为主，等待市场消化关税消息，不宜追高',
        '📌 周二：Trump 国情咨文，关注关税和AI政策表态',
        '📌 周三：NVDA 财报是本周最大催化剂，结果出来前控制仓位',
        f'📌 整体：情绪指数 {fg}/100，{"可关注超跌优质股低吸机会" if fg<40 else "市场偏热，谨慎追高"}',
    ]

    risks = [
        '🚨 Trump 可能宣布更多关税或贸易措施（国情咨文）',
        '🚨 NVDA 财报若不及预期，AI板块可能大幅回调',
        '⚠️ 美联储官员讲话可能影响降息预期',
    ]

    return {
        'events':   events,
        'outlook':  {'mood': mood, 'mood_emoji': mood_emoji, 'mood_class': mood_class, 'items': outlook_items},
        'core_stocks': core_stocks,
        'strategy': strategy,
        'risks':    risks,
    }


def generate_telegram_summary(analysis: dict, headlines: list, market_data: dict) -> str:
    """生成 Telegram 推送摘要"""
    now  = datetime.now()
    fg   = market_data.get('fear_greed', {})
    idx  = market_data.get('indices', {})

    def fmt(v): return f"{'+'if v>=0 else ''}{v:.2f}%"
    def arr(v): return '🔺' if v>0 else '🔻'

    out = analysis['outlook']
    lines = [
        f"📅 **周末市场总结** | {now.strftime('%m/%d')} 周一",
        "━━━━━━━━━━━━━━━━",
        f"\n{out['mood_emoji']} 本周开盘展望：**{out['mood']}**",
        f"{fg.get('emoji','😐')} 情绪指数：{fg.get('label_zh','--')} ({fg.get('value','--')}/100)",
        "",
    ]

    # 上周收盘
    lines.append("📊 **上周末收盘**")
    for t, name in [('SPY','标普500'),('QQQ','纳斯达克'),('DIA','道指')]:
        q = idx.get(t, {})
        if q:
            lines.append(f"  {arr(q['change_pct'])} {name} {fmt(q['change_pct'])}")

    # 事件
    lines.append("\n🗞️ **周末重大事件**")
    for e in analysis['events'][:3]:
        lines.append(f"  {e['emoji']} {e['title']}: {e['detail'][:50]}...")
        lines.append(f"     → {e['impact']}")

    # 预判
    lines.append("\n🎯 **今晚开盘预判**")
    for item in out['items']:
        lines.append(f"  {item}")

    # 本周策略
    lines.append("\n📌 **本周策略**")
    for s in analysis['strategy'][:3]:
        lines.append(f"  {s}")

    lines.append(f"\n📋 完整周报：https://wssxwz.github.io/stock-strategy/")
    lines.append("━━━━━━━━━━━━━━━━")
    lines.append("_数据延迟15min，仅供参考_")

    return '\n'.join(lines)


def run():
    now = datetime.now()
    # 计算周报标签（本周一日期）
    monday = now - timedelta(days=now.weekday())
    week_label = f"{monday.strftime('%Y/%m/%d')} 当周"
    date_str   = now.strftime('%Y-%m-%d')

    print(f"📅 生成周末市场总结 {week_label}...")

    # 1. 拉市场数据
    print("  采集市场数据...")
    indices  = get_batch_quotes(['SPY','QQQ','DIA','IWM','VIX'])
    fg       = get_fear_greed()
    sectors  = get_sector_performance()
    market_data = {'indices': indices, 'fear_greed': fg, 'sectors': sectors}

    # 2. 抓新闻
    print("  获取财经新闻...")
    headlines = fetch_news_headlines()
    print(f"  获取到 {len(headlines)} 条新闻")

    # 3. 分析生成
    print("  生成分析报告...")
    analysis = analyze_headlines(headlines, market_data)

    # 4. 生成 Telegram 摘要
    tg_msg = generate_telegram_summary(analysis, headlines, market_data)

    # 5. 构建周报 JSON
    report = {
        'week_label':    week_label,
        'date':          date_str,
        'generated_at':  now.isoformat(),
        'weekend_events': analysis['events'],
        'market_outlook': analysis['outlook'],
        'core_stocks':    analysis['core_stocks'],
        'strategy':       analysis['strategy'],
        'risks':          analysis['risks'],
        'raw_content':    tg_msg,
        'market_data': {
            'indices':    indices,
            'fear_greed': fg,
        },
        'headlines': headlines[:10],
    }

    # 6. 保存到 Dashboard
    reports = load_reports()
    # 同一周的周报去重（覆盖）
    reports = [r for r in reports if r.get('week_label') != week_label]
    reports.insert(0, report)
    reports = reports[:20]  # 最多保留20周
    save_reports(reports)
    print(f"  ✅ 已保存周报到 {WEEKLY_FILE}")

    # 7. 同步更新 root index 的 weekly_reports.json
    root_path = os.path.join(os.path.dirname(__file__), '../weekly_reports.json')
    with open(root_path, 'w') as f:
        json.dump(reports, f, indent=2, default=str)

    # 8. 输出 Telegram 推送
    print(f"\nWEEKLY_REPORT_START")
    print(tg_msg)
    print(f"WEEKLY_REPORT_END")

    return tg_msg


if __name__ == '__main__':
    run()
