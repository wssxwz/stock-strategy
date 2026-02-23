"""
经济日历 + 财报日历数据模块
生成本周 + 未来4周的重要事件
供 Dashboard calendar.json 使用
"""
import warnings
warnings.filterwarnings('ignore')

import yfinance as yf
import json, os
from datetime import datetime, timedelta, date

DASHBOARD_DIR = os.path.join(os.path.dirname(__file__), '../dashboard')
CALENDAR_FILE = os.path.join(DASHBOARD_DIR, 'calendar.json')
ROOT_CALENDAR  = os.path.join(os.path.dirname(__file__), '../calendar.json')

# ── 核心关注股票（全量）──
WATCHLIST_ALL = [
    # Tier1 核心持仓
    'TSLA','GOOGL','NVDA','META',
    # Tier2 重点关注
    'RKLB','ASTS','PLTR','AMD','AVGO','LLY','AMZN','MSFT','AAPL',
    'CRWD','NOW','DDOG','NEM','GDX',
    # 纳指100 重要成分
    'NFLX','INTC','QCOM','MU','AMAT','LRCX','TXN',
    'ADBE','CRM','PANW','SNPS','KLAC','MRVL','MELI',
]

TIER1 = {'TSLA','GOOGL','NVDA','META'}
TIER2 = {'RKLB','ASTS','PLTR','AMD','AVGO','LLY','AMZN','MSFT','AAPL','CRWD','NOW','DDOG','NEM','GDX'}

# ── 固定经济日历（每月/每周规律发布）──
# 格式: (月日偏移规则, 事件名, 重要性, 影响)
# 这里用"已知即将发布日期"硬编码 + 动态规则两种方式
KNOWN_MACRO_EVENTS_2026 = [
    # 2月
    {'date':'2026-02-25', 'event':'耐用品订单 Jan', 'category':'macro', 'importance':3, 'impact':'neutral', 'emoji':'🏭'},
    {'date':'2026-02-26', 'event':'GDP Q4 终值', 'category':'macro', 'importance':5, 'impact':'neutral', 'emoji':'📊'},
    {'date':'2026-02-27', 'event':'PCE 物价指数 Jan', 'category':'macro', 'importance':5, 'impact':'bearish', 'emoji':'💰', 'note':'Fed最关注通胀指标'},
    {'date':'2026-02-27', 'event':'初请失业金人数', 'category':'macro', 'importance':3, 'impact':'neutral', 'emoji':'👷'},
    {'date':'2026-02-28', 'event':'密歇根消费者信心终值', 'category':'macro', 'importance':3, 'impact':'neutral', 'emoji':'😊'},
    # 3月
    {'date':'2026-03-04', 'event':'ISM 制造业 PMI', 'category':'macro', 'importance':4, 'impact':'neutral', 'emoji':'🏗️'},
    {'date':'2026-03-06', 'event':'非农就业人数 Feb', 'category':'macro', 'importance':5, 'impact':'neutral', 'emoji':'💼', 'note':'月度最重要就业数据'},
    {'date':'2026-03-06', 'event':'失业率 Feb', 'category':'macro', 'importance':4, 'impact':'neutral', 'emoji':'📉'},
    {'date':'2026-03-10', 'event':'CPI 通胀 Feb', 'category':'macro', 'importance':5, 'impact':'bearish', 'emoji':'🔥', 'note':'影响降息时间表'},
    {'date':'2026-03-12', 'event':'PPI 生产者物价 Feb', 'category':'macro', 'importance':4, 'impact':'neutral', 'emoji':'🏪'},
    {'date':'2026-03-17', 'event':'零售销售 Feb', 'category':'macro', 'importance':4, 'impact':'neutral', 'emoji':'🛒'},
    {'date':'2026-03-18', 'event':'FOMC 利率决议', 'category':'fomc', 'importance':5, 'impact':'neutral', 'emoji':'🏦', 'note':'Fed是否暗示降息'},
    {'date':'2026-03-19', 'event':'FOMC 新闻发布会', 'category':'fomc', 'importance':5, 'impact':'neutral', 'emoji':'🎙️'},
    {'date':'2026-03-26', 'event':'GDP Q4 修正版', 'category':'macro', 'importance':4, 'impact':'neutral', 'emoji':'📊'},
    {'date':'2026-03-27', 'event':'PCE 物价指数 Feb', 'category':'macro', 'importance':5, 'impact':'bearish', 'emoji':'💰'},
    # 4月
    {'date':'2026-04-03', 'event':'非农就业 Mar', 'category':'macro', 'importance':5, 'impact':'neutral', 'emoji':'💼'},
    {'date':'2026-04-10', 'event':'CPI 通胀 Mar', 'category':'macro', 'importance':5, 'impact':'neutral', 'emoji':'🔥'},
    {'date':'2026-04-16', 'event':'零售销售 Mar', 'category':'macro', 'importance':4, 'impact':'neutral', 'emoji':'🛒'},
    {'date':'2026-04-28', 'event':'GDP Q1 初值', 'category':'macro', 'importance':5, 'impact':'neutral', 'emoji':'📈'},
    {'date':'2026-04-29', 'event':'FOMC 利率决议', 'category':'fomc', 'importance':5, 'impact':'neutral', 'emoji':'🏦'},
    # 特殊事件
    {'date':'2026-02-25', 'event':'Trump 国情咨文', 'category':'political', 'importance':5, 'impact':'bearish', 'emoji':'🇺🇸', 'note':'关税/AI政策表态'},
]


def get_earnings_timing(info: dict) -> str:
    """根据 earningsTimestamp 判断盘前/盘后/未知"""
    ts = info.get('earningsTimestamp')
    if not ts:
        return ''
    try:
        import pytz
        et_tz = pytz.timezone('America/New_York')
        dt_et = datetime.fromtimestamp(ts, tz=pytz.utc).astimezone(et_tz)
        h = dt_et.hour
        if h < 9 or (h == 9 and dt_et.minute < 30):
            return 'BMO'   # Before Market Open 盘前
        elif h >= 16:
            return 'AMC'   # After Market Close 盘后
        else:
            return 'BMO'   # 少数情况盘中，当盘前处理
    except Exception:
        return ''


def get_earnings_details(ticker: str) -> dict:
    """获取单只股票的详细财报数据（预期/实际/同比/gap）"""
    try:
        tk = yf.Ticker(ticker)
        info = tk.info
        cal = tk.calendar
        
        # 基础信息
        result = {
            'ticker': ticker,
            'company_name': info.get('longName', ticker),
            'sector': info.get('sector', ''),
            'market_cap': info.get('marketCap'),
        }
        
        # 财报日期和时间
        earnings_dates = cal.get('Earnings Date', [])
        if earnings_dates:
            ed = earnings_dates[0]
            if isinstance(ed, datetime):
                ed = ed.date()
            result['earnings_date'] = str(ed)
            result['timing'] = get_earnings_timing(info)
        
        # 预期值
        result['eps_estimate'] = cal.get('Earnings Average')
        result['eps_high']    = cal.get('Earnings High')
        result['eps_low']     = cal.get('Earnings Low')
        result['rev_estimate']= cal.get('Revenue Average')
        result['rev_high']    = cal.get('Revenue High')
        result['rev_low']     = cal.get('Revenue Low')
        
        # 获取历史财报（找去年同期实际值）
        try:
            earnings = tk.earnings
            if earnings is not None and len(earnings) > 0:
                # 最新一期
                latest = earnings.iloc[-1]
                result['eps_actual_latest'] = latest.get('EPS Estimate')  # yfinance 这个字段名可能有变
                result['rev_actual_latest'] = latest.get('Revenue Estimate')
        except Exception:
            pass
        
        # 尝试从 earnings_history 获取实际值
        try:
            hist = tk.earnings_history
            if hist is not None and len(hist) > 0:
                latest_hist = hist.iloc[-1]
                # 如果财报已发布，会有 EPS Actual
                if 'EPS Actual' in latest_hist:
                    result['eps_actual'] = latest_hist['EPS Actual']
                    result['eps_estimate_hist'] = latest_hist.get('EPS Estimate')
                    result['eps_surprise'] = latest_hist.get('Surprise(%)')
                if 'Revenue Actual' in latest_hist:
                    result['rev_actual'] = latest_hist['Revenue Actual']
                    result['rev_estimate_hist'] = latest_hist.get('Revenue Estimate')
        except Exception:
            pass
        
        # 去年同期数据（用于同比）
        try:
            # yfinance 不直接提供 YoY，需要从 quarterly_finances 或 income_stmt 推算
            # 这里简化处理，从 info 里拿 growth 字段
            result['eps_growth_yoy'] = info.get('earningsGrowth')
            result['rev_growth_yoy'] = info.get('revenueGrowth')
        except Exception:
            pass
        
        return result
    except Exception as e:
        print(f"  获取 {ticker} 财报详情失败: {e}")
        return {}


def get_earnings_calendar(weeks_ahead: int = 6) -> list:
    """从 yfinance 拉取未来N周的财报日历"""
    today = date.today()
    cutoff = today + timedelta(weeks=weeks_ahead)
    events = []

    print(f"  获取 {len(WATCHLIST_ALL)} 只股票财报日期...")
    seen = set()

    for ticker in WATCHLIST_ALL:
        try:
            tk  = yf.Ticker(ticker)
            cal = tk.calendar
            earnings_dates = cal.get('Earnings Date', [])
            if not earnings_dates:
                continue
            ed = earnings_dates[0]
            if isinstance(ed, datetime):
                ed = ed.date()
            if ed < today or ed > cutoff:
                continue
            key = f"{ticker}_{ed}"
            if key in seen:
                continue
            seen.add(key)

            # 盘前/盘后
            try:
                info   = tk.info
                timing = get_earnings_timing(info)
            except Exception:
                timing = ''

            timing_zh  = {'BMO': '盘前📈', 'AMC': '盘后🌙', '': '时间待定'}.get(timing, '')
            timing_tag = f" [{timing_zh}]" if timing_zh else ''

            eps_avg  = cal.get('Earnings Average')
            eps_high = cal.get('Earnings High')
            eps_low  = cal.get('Earnings Low')

            is_tier1   = ticker in TIER1
            is_tier2   = ticker in TIER2
            importance = 5 if is_tier1 else (4 if is_tier2 else 3)

            tag = ''
            if is_tier1:   tag = '⭐ 核心持仓'
            elif is_tier2: tag = '🎯 重点关注'

            note_parts = []
            if eps_avg:    note_parts.append(f"EPS预期 ${eps_avg:.2f}")
            if timing_zh:  note_parts.append(timing_zh)

            events.append({
                'date':       str(ed),
                'event':      f"{ticker} 财报{timing_tag}",
                'ticker':     ticker,
                'category':   'earnings',
                'importance': importance,
                'impact':     'neutral',
                'emoji':      '📋',
                'tag':        tag,
                'timing':     timing,
                'timing_zh':  timing_zh,
                'eps_est':    round(eps_avg, 3) if eps_avg else None,
                'eps_range':  f"${eps_low:.2f}~${eps_high:.2f}" if eps_low and eps_high else None,
                'note':       ' · '.join(note_parts),
            })
        except Exception:
            pass

    return sorted(events, key=lambda x: x['date'])


def get_macro_calendar(weeks_ahead: int = 6) -> list:
    """返回未来N周的宏观经济事件"""
    today = date.today()
    cutoff = today + timedelta(weeks=weeks_ahead)

    events = []
    for ev in KNOWN_MACRO_EVENTS_2026:
        ev_date = date.fromisoformat(ev['date'])
        if ev_date < today - timedelta(days=1) or ev_date > cutoff:
            continue
        events.append(ev)

    return sorted(events, key=lambda x: x['date'])


def build_calendar(weeks_ahead: int = 6) -> dict:
    """合并财报 + 宏观，按日期分组，输出 Dashboard 用的 JSON"""
    today = date.today()

    print("  拉取财报日历...")
    earnings = get_earnings_calendar(weeks_ahead)
    print(f"  → {len(earnings)} 条财报事件")

    print("  获取财报详情（预期/实际/同比）...")
    earnings_details = {}
    for ev in earnings:
        ticker = ev.get('ticker')
        if ticker:
            details = get_earnings_details(ticker)
            if details:
                earnings_details[ticker] = details
    print(f"  → {len(earnings_details)} 只股票详情")

    print("  加载宏观经济日历...")
    macro = get_macro_calendar(weeks_ahead)
    print(f"  → {len(macro)} 条宏观事件")

    all_events = earnings + macro
    all_events.sort(key=lambda x: (x['date'], -x['importance']))

    # 按日期分组
    by_date = {}
    for ev in all_events:
        d = ev['date']
        if d not in by_date:
            by_date[d] = []
        by_date[d].append(ev)

    # 本周事件（高亮）
    week_start = today
    week_end   = today + timedelta(days=7)
    this_week  = [ev for ev in all_events
                  if week_start <= date.fromisoformat(ev['date']) <= week_end]

    # 核心持仓财报（未来6周内）
    core_earnings = [ev for ev in earnings if ev.get('tag') == '⭐ 核心持仓']

    return {
        'generated_at':     datetime.now().isoformat(),
        'this_week':        this_week,
        'core_earnings':    core_earnings,
        'by_date':          by_date,
        'all_events':       all_events,
        'earnings_details': earnings_details,
    }


def run():
    print("📅 更新经济日历 + 财报日历...")
    calendar = build_calendar(weeks_ahead=8)

    # 写入 dashboard/
    with open(CALENDAR_FILE, 'w') as f:
        json.dump(calendar, f, indent=2, default=str)
    print(f"  ✅ {CALENDAR_FILE}")

    # 写入根目录
    with open(ROOT_CALENDAR, 'w') as f:
        json.dump(calendar, f, indent=2, default=str)
    print(f"  ✅ {ROOT_CALENDAR}")

    print(f"\n本周事件 ({len(calendar['this_week'])} 条):")
    for ev in calendar['this_week']:
        print(f"  {ev['date']} {ev['emoji']} {ev['event']} (重要性:{ev['importance']})")

    return calendar


if __name__ == '__main__':
    run()
