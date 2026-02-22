"""
早盘摘要 Job - 每天 7:50 北京时间 (UTC 23:50) 推送
手机一屏看完的精华摘要
"""
import sys, os, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from market_data import (
    get_batch_quotes, get_fear_greed, get_sector_performance,
    INDICES, COMMODITIES, FOREX, save_daily_data
)
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import kb
from datetime import datetime
import json


def arrow(pct: float) -> str:
    if pct > 1:    return '🚀'
    if pct > 0.3:  return '📈'
    if pct > 0:    return '↗️'
    if pct > -0.3: return '↘️'
    if pct > -1:   return '📉'
    return '🔻'


def fmt_pct(pct: float) -> str:
    return f"{'+' if pct >= 0 else ''}{pct:.2f}%"


def generate_morning_brief() -> str:
    now = datetime.now()
    date_str = now.strftime('%Y年%m月%d日')
    weekdays = ['周一','周二','周三','周四','周五','周六','周日']
    weekday = weekdays[now.weekday()]

    print("📡 采集市场数据...")

    # 1. 指数行情
    idx_quotes = get_batch_quotes(list(INDICES.keys()))

    # 2. 大宗商品
    cmd_quotes = get_batch_quotes(list(COMMODITIES.keys()))

    # 3. 恐惧贪婪
    fg = get_fear_greed()

    # 4. 板块表现
    sectors = get_sector_performance()

    # ── 构建摘要消息 ──
    lines = []
    lines.append(f"🌅 **早盘摘要** | {date_str} {weekday}")
    lines.append("━━━━━━━━━━━━━━━━")

    # 市场情绪
    lines.append(f"\n{fg['emoji']} **市场情绪：{fg['label_zh']}** ({fg['value']}/100)")

    # 美股指数
    lines.append("\n📊 **美股昨夜收盘**")
    for ticker, name in INDICES.items():
        if ticker == 'VIX':
            continue
        if ticker in idx_quotes:
            q = idx_quotes[ticker]
            lines.append(f"  {arrow(q['change_pct'])} {name}  {fmt_pct(q['change_pct'])}")

    # VIX
    if 'VIX' in idx_quotes:
        vix = idx_quotes['VIX']
        vix_level = '低波动' if vix['price'] < 15 else ('正常' if vix['price'] < 25 else ('高波动⚠️' if vix['price'] < 35 else '极高波动🚨'))
        lines.append(f"  📉 VIX {vix['price']:.1f}  ({vix_level})")

    # 大宗商品
    lines.append("\n🛢️ **大宗商品**")
    for ticker, name in COMMODITIES.items():
        if ticker in cmd_quotes:
            q = cmd_quotes[ticker]
            lines.append(f"  {arrow(q['change_pct'])} {name}  {fmt_pct(q['change_pct'])}")

    # 板块强弱 TOP3 / BOTTOM3
    if sectors:
        sector_list = list(sectors.items())
        lines.append("\n🗂️ **板块表现**")
        top3    = sector_list[:3]
        bottom3 = sector_list[-3:]
        for etf, d in top3:
            lines.append(f"  💪 {d['name']}  {fmt_pct(d['change_pct'])}")
        lines.append("  ···")
        for etf, d in bottom3:
            lines.append(f"  🩸 {d['name']}  {fmt_pct(d['change_pct'])}")

    # 核心持仓快照
    core = kb.get_core_holdings()
    core_quotes = get_batch_quotes(core)
    if core_quotes:
        lines.append("\n⭐ **核心持仓动态**")
        for t in core:
            if t in core_quotes:
                q = core_quotes[t]
                lines.append(f"  {arrow(q['change_pct'])} {t}  {fmt_pct(q['change_pct'])}")

    # 今日重要提示占位（deep_analysis 会补充）
    lines.append("\n📋 **今日重点关注**")
    lines.append("  → 详细策略分析 8:10 推送")
    lines.append(f"  → 平台：https://wssxwz.github.io/stock-strategy/")

    lines.append("\n━━━━━━━━━━━━━━━━")
    lines.append("_数据延迟15min，仅供参考_")

    msg = '\n'.join(lines)

    # 保存今日数据
    save_daily_data({
        'morning_brief': {
            'generated_at': now.isoformat(),
            'indices':      idx_quotes,
            'commodities':  cmd_quotes,
            'fear_greed':   fg,
            'sectors':      sectors,
        }
    })

    return msg


if __name__ == '__main__':
    print("生成早盘摘要...")
    msg = generate_morning_brief()
    print("\n" + "="*50)
    print(msg)
    print("="*50)
    print("\nMORNING_BRIEF_START")
    print(msg)
    print("MORNING_BRIEF_END")
