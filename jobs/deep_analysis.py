"""
深度早报 Job - 每天 8:10 北京时间 (UTC 0:10) 生成
生成 HTML 报告 + Telegram 精华推送
"""
import sys, os, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from market_data import (
    get_batch_quotes, get_fear_greed, get_sector_performance,
    INDICES, COMMODITIES, SECTORS, save_daily_data, load_daily_data
)
from datetime import datetime
import argparse
import json


def get_market_overview() -> dict:
    """综合市场概况"""
    idx   = get_batch_quotes(list(INDICES.keys()))
    cmd   = get_batch_quotes(list(COMMODITIES.keys()))
    sects = get_sector_performance()
    fg    = get_fear_greed()

    # 市场整体方向
    sp500_pct = idx.get('^GSPC', {}).get('change_pct', 0)
    qqq_pct   = idx.get('^NDX', {}).get('change_pct', 0)
    vix_val   = idx.get('^VIX', {}).get('price', 20)

    if sp500_pct > 0.5 and qqq_pct > 0.5:
        market_mood = '多头'
        mood_emoji  = '🟢'
    elif sp500_pct < -0.5 and qqq_pct < -0.5:
        market_mood = '空头'
        mood_emoji  = '🔴'
    else:
        market_mood = '震荡'
        mood_emoji  = '🟡'

    return {
        'indices':     idx,
        'commodities': cmd,
        'sectors':     sects,
        'fear_greed':  fg,
        'market_mood': market_mood,
        'mood_emoji':  mood_emoji,
        'sp500_pct':   sp500_pct,
        'qqq_pct':     qqq_pct,
        'vix':         vix_val,
    }


def get_operation_advice(overview: dict) -> dict:
    """
    基于市场状态生成操作建议
    这里用规则引擎，后续可接入AI
    """
    fg_value   = overview['fear_greed']['value']
    sp500_pct  = overview['sp500_pct']
    vix        = overview['vix']
    market_mood = overview['market_mood']
    sectors    = overview['sectors']

    advices = []
    risks   = []

    # 仓位建议
    if fg_value < 25:
        advices.append('💎 市场极度恐惧，历史上是较好的买入窗口，可逐步加仓')
    elif fg_value < 45:
        advices.append('📊 市场偏恐惧，可以寻找超卖的优质个股买入机会')
    elif fg_value > 75:
        advices.append('⚠️ 市场极度贪婪，注意风险，控制仓位不宜追高')
    elif fg_value > 55:
        advices.append('🎯 市场偏乐观，持有为主，谨慎追高')
    else:
        advices.append('⚖️ 市场中性，按策略信号操作')

    # VIX 风险提示
    if vix > 30:
        risks.append(f'🚨 VIX={vix:.1f} 高于30，市场波动剧烈，降低单笔仓位')
    elif vix > 20:
        risks.append(f'⚠️ VIX={vix:.1f} 偏高，注意止损执行')

    # 板块建议
    if sectors:
        top_sector = list(sectors.items())[0]
        bot_sector = list(sectors.items())[-1]
        advices.append(f'🏆 最强板块：{top_sector[1]["name"]} ({top_sector[1]["change_pct"]:+.1f}%)，可关注相关个股')
        if bot_sector[1]['change_pct'] < -1:
            risks.append(f'📉 {bot_sector[1]["name"]} 板块走弱 ({bot_sector[1]["change_pct"]:+.1f}%)，持仓注意')

    # 趋势建议
    if market_mood == '多头':
        advices.append('🚀 整体多头趋势，持仓为主，信号触发可加仓')
    elif market_mood == '空头':
        advices.append('🛡️ 整体偏空，降低仓位，以防守为主')

    return {
        'market_mood':  market_mood,
        'advices':      advices,
        'risks':        risks,
        'fg_value':     fg_value,
        'fg_label_zh':  overview['fear_greed']['label_zh'],
    }


def generate_telegram_msg(overview: dict, advice: dict) -> str:
    """生成 Telegram 精华推送（早餐时看）

    Goal: concise but punchy. Focus on *last night's tape* + actionable read.
    """
    now = datetime.now()

    def fmt(pct):
        try:
            pct = float(pct)
        except Exception:
            pct = 0.0
        return f"{('+' if pct >= 0 else '')}{pct:.2f}%"

    def arr(pct):
        try:
            pct = float(pct)
        except Exception:
            pct = 0.0
        return '🔺' if pct > 0 else '🔻'

    idx = overview.get('indices', {}) or {}
    sects = overview.get('sectors', {}) or {}

    spy = idx.get('^GSPC', {})
    qqq = idx.get('^NDX', {})
    dia = idx.get('^DJI', {})
    iwm = idx.get('^RUT', {})
    vix = idx.get('^VIX', {})

    fg = overview.get('fear_greed', {}) or {}

    # Quick sector leaders/laggards
    top2 = []
    bot2 = []
    if sects:
        sl = list(sects.items())
        top2 = sl[:2]
        bot2 = sl[-2:]

    # Tape read (simple but useful)
    risk_off = False
    try:
        risk_off = float(qqq.get('change_pct', 0)) < float(spy.get('change_pct', 0)) - 0.3
    except Exception:
        pass

    # build
    lines = [
        f"📊 **深度早报（精读版）** | {now.strftime('%m/%d')}",
        "━━━━━━━━━━━━━━━━",
        f"\n{overview['mood_emoji']} 昨夜主线：**{overview['market_mood']}**｜{fg.get('emoji','')} 情绪：**{fg.get('label_zh','')}** {fg.get('value','-')}",
        "",
        "📌 **大盘复盘（昨夜）**",
        f"  {arr(spy.get('change_pct',0))} SPY {fmt(spy.get('change_pct',0))}｜{arr(qqq.get('change_pct',0))} QQQ {fmt(qqq.get('change_pct',0))}｜{arr(dia.get('change_pct',0))} 道指 {fmt(dia.get('change_pct',0))}",
        f"  {arr(iwm.get('change_pct',0))} IWM {fmt(iwm.get('change_pct',0))}｜VIX {fmt(vix.get('change_pct',0))} → {vix.get('price','-')}",
    ]

    if risk_off:
        lines.append("  🧭 风格：纳指明显弱于标普 → **偏风险规避/高β承压**")
    else:
        lines.append("  🧭 风格：权重与成长分化不大 → **以轮动为主**")

    if top2 or bot2:
        lines.append("\n🗂️ **板块轮动（强→弱）**")
        for _, d in top2:
            lines.append(f"  💪 {d['name']} {fmt(d['change_pct'])}")
        if bot2:
            lines.append("  ···")
            for _, d in bot2:
                lines.append(f"  🩸 {d['name']} {fmt(d['change_pct'])}")

    # Actionable plan (short)
    lines.append("\n🎯 **今日策略（简洁版）**")
    # pick 2-3 advices but rewrite to be more actionable
    fg_val = fg.get('value', None)
    try:
        fg_val = int(fg_val)
    except Exception:
        fg_val = None

    if fg_val is not None and fg_val <= 25:
        lines.append("  • 情绪极恐：优先抓**高质量回撤**，分批试错；仓位从小到大")
    elif overview.get('market_mood') == '空头':
        lines.append("  • 偏空：以防守为主，信号也要更挑剔（宁可少做）")
    else:
        lines.append("  • 震荡：不追涨，等回撤到位/结构明确再出手")

    if advice.get('risks'):
        # keep only the first risk line
        lines.append(f"  • 风险：{advice['risks'][0]}")

    lines.append("\n⏰ **关注时间点（北京）**")
    lines.append("  • 21:30 开盘前后波动增大（数据/财报集中时段）")

    lines.append(f"\n📋 完整报告：https://wssxwz.github.io/stock-strategy/")
    lines.append("\n_数据延迟约15min，仅供参考_")

    return '\n'.join(lines)


def generate_html_report(overview: dict, advice: dict, date_str: str) -> str:
    """生成 HTML 格式完整报告"""
    now = datetime.now()
    sects = overview['sectors']
    idx   = overview['indices']
    cmd   = overview['commodities']

    def fmt(pct, colored=True):
        color = '#22c55e' if pct >= 0 else '#ef4444'
        sign  = '+' if pct >= 0 else ''
        val   = f"{sign}{pct:.2f}%"
        return f'<span style="color:{color}">{val}</span>' if colored else val

    # 板块热力图 HTML
    sector_html = ''
    if sects:
        max_abs = max(abs(d['change_pct']) for d in sects.values()) or 1
        for etf, d in sects.items():
            pct  = d['change_pct']
            intensity = abs(pct) / max_abs
            if pct > 0:
                bg = f"rgba(34,197,94,{0.2 + 0.6*intensity})"
            else:
                bg = f"rgba(239,68,68,{0.2 + 0.6*intensity})"
            sector_html += f'''
            <div style="background:{bg};padding:12px 8px;border-radius:10px;text-align:center;min-width:80px">
                <div style="font-weight:700;font-size:14px">{d["name"]}</div>
                <div style="font-size:18px;font-weight:800;margin-top:4px">{"+" if pct>=0 else ""}{pct:.2f}%</div>
            </div>'''

    # 建议 HTML
    advice_html = ''.join(f'<li style="margin:8px 0">{a}</li>' for a in advice['advices'])
    risk_html   = ''.join(f'<li style="margin:8px 0;color:#f59e0b">{r}</li>' for r in advice['risks'])

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>深度早报 {date_str}</title>
  <style>
    * {{ box-sizing:border-box; margin:0; padding:0; }}
    body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
            background:#0f172a; color:#f1f5f9; padding:24px; }}
    .container {{ max-width:1000px; margin:0 auto; }}
    h1 {{ font-size:26px; margin-bottom:6px; }}
    .subtitle {{ color:#94a3b8; font-size:14px; margin-bottom:30px; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:20px; margin-bottom:24px; }}
    .card {{ background:#1e293b; border-radius:14px; padding:22px; }}
    .card h2 {{ font-size:16px; color:#94a3b8; margin-bottom:14px; text-transform:uppercase; letter-spacing:.5px; }}
    .stat-row {{ display:flex; justify-content:space-between; padding:8px 0; border-bottom:1px solid #334155; font-size:15px; }}
    .stat-row:last-child {{ border:none; }}
    .green {{ color:#22c55e; }} .red {{ color:#ef4444; }}
    .mood-badge {{ display:inline-block; padding:6px 18px; border-radius:30px; font-weight:700; font-size:20px;
                   background:{'#1a4731' if overview["market_mood"]=="多头" else ('#4a1919' if overview["market_mood"]=="空头" else '#3a3000')};
                   color:{'#22c55e' if overview["market_mood"]=="多头" else ('#ef4444' if overview["market_mood"]=="空头" else '#eab308')}; }}
    .fg-bar {{ height:12px; border-radius:6px; background:linear-gradient(to right,#ef4444,#eab308,#22c55e);
               margin:10px 0; position:relative; }}
    .fg-bar::after {{ content:''; position:absolute; top:-3px; width:18px; height:18px;
                      background:white; border-radius:50%; border:3px solid #1e293b;
                      left:calc({overview["fear_greed"]["value"]}% - 9px); }}
    .sectors {{ display:flex; flex-wrap:wrap; gap:10px; }}
    ul {{ list-style:none; padding-left:4px; }}
    .advice-list li::before {{ content:"→ "; color:#3b82f6; }}
    .risk-list li::before {{ content:"⚠️ "; }}
    .report-time {{ margin-top:30px; text-align:right; font-size:13px; color:#475569; }}
  </style>
</head>
<body>
<div class="container">
  <h1>📊 深度早报</h1>
  <div class="subtitle">{date_str} | 生成时间: {now.strftime('%H:%M')} 北京时间 | 数据延迟约15分钟</div>

  <!-- 市场情绪 -->
  <div class="card" style="margin-bottom:20px">
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:16px">
      <div>
        <div style="color:#94a3b8;font-size:13px;margin-bottom:6px">市场方向</div>
        <div class="mood-badge">{overview["mood_emoji"]} {overview["market_mood"]}</div>
      </div>
      <div style="flex:1;min-width:200px;max-width:360px">
        <div style="color:#94a3b8;font-size:13px;margin-bottom:6px">
          恐惧贪婪指数 — {overview["fear_greed"]["emoji"]} {overview["fear_greed"]["label_zh"]} ({overview["fear_greed"]["value"]})
        </div>
        <div class="fg-bar"></div>
        <div style="display:flex;justify-content:space-between;font-size:12px;color:#475569">
          <span>极度恐惧</span><span>中性</span><span>极度贪婪</span>
        </div>
      </div>
    </div>
  </div>

  <div class="grid">
    <!-- 指数 -->
    <div class="card">
      <h2>📈 美股指数 (昨夜)</h2>
      {''.join(f'<div class="stat-row"><span>{name}</span><span class="{"green" if idx.get(t,{}).get("change_pct",0)>=0 else "red"}">{("+" if idx.get(t,{}).get("change_pct",0)>=0 else "")}{idx.get(t,{}).get("change_pct",0):.2f}%</span></div>' for t, name in [("^GSPC","标普500"),("^NDX","纳斯达克100"),("^DJI","道琼斯"),("^RUT","罗素2000"),("^VIX","VIX恐慌指数")]  if t in idx)}
    </div>

    <!-- 大宗商品 -->
    <div class="card">
      <h2>🛢️ 大宗商品</h2>
      {''.join(f'<div class="stat-row"><span>{name}</span><span class="{"green" if cmd.get(t,{}).get("change_pct",0)>=0 else "red"}">{("+" if cmd.get(t,{}).get("change_pct",0)>=0 else "")}{cmd.get(t,{}).get("change_pct",0):.2f}%</span></div>' for t, name in [("GC=F","黄金"),("CL=F","原油WTI"),("SI=F","白银"),("NG=F","天然气")] if t in cmd)}
    </div>
  </div>

  <!-- 板块热力图 -->
  <div class="card" style="margin-bottom:20px">
    <h2>🗂️ 板块热力图</h2>
    <div class="sectors">{sector_html}</div>
  </div>

  <!-- 操作建议 -->
  <div class="grid">
    <div class="card">
      <h2>💡 今日操作建议</h2>
      <ul class="advice-list">{advice_html}</ul>
    </div>
    {'<div class="card"><h2>⚠️ 风险提示</h2><ul class="risk-list">' + risk_html + '</ul></div>' if advice['risks'] else ''}
  </div>

  <div class="report-time">报告生成于 {now.strftime('%Y-%m-%d %H:%M')} | 数据来源: Yahoo Finance / alternative.me</div>
</div>
</body>
</html>"""

    return html


def run(date_str: str | None = None, update_latest: bool = True, save_daily: bool = True):
    now = datetime.now()
    today_str = now.strftime('%Y-%m-%d')
    date_str = date_str or today_str

    print(f"📊 生成深度早报 {date_str}...")

    # Note: for backfill (--date in the past), we still fetch current market data.
    # This is mainly to ensure dashboard report continuity (missing file) rather than a strict historical replay.
    overview = get_market_overview()
    advice   = get_operation_advice(overview)

    # 生成 Telegram 精华消息
    tg_msg = generate_telegram_msg(overview, advice)

    # 生成 HTML 报告
    html = generate_html_report(overview, advice, date_str)
    html_path = os.path.join(os.path.dirname(__file__), f'../dashboard/reports/{date_str}.html')
    os.makedirs(os.path.dirname(html_path), exist_ok=True)
    with open(html_path, 'w') as f:
        f.write(html)

    # 更新 latest-report.html（默认仅当天更新；回补历史时建议关闭）
    if update_latest:
        latest_path = os.path.join(os.path.dirname(__file__), '../dashboard/latest-report.html')
        with open(latest_path, 'w') as f:
            f.write(html)

    # 保存数据
    if save_daily:
        save_daily_data({
            'deep_analysis': {
                'generated_at': now.isoformat(),
                'market_mood':  overview['market_mood'],
                'fear_greed':   overview['fear_greed'],
                'advice':       advice,
            }
        }, date_str)

    print("\nDEEP_ANALYSIS_START")
    print(tg_msg)
    print("DEEP_ANALYSIS_END")
    print(f"\n✅ HTML 报告已保存: {html_path}")


def _parse_args():
    ap = argparse.ArgumentParser(description='深度早报生成器')
    ap.add_argument('--date', help='指定报告日期（YYYY-MM-DD），用于回补缺失报告文件', default=None)
    ap.add_argument('--update-latest', action='store_true', help='同时更新 dashboard/latest-report.html（默认仅当天）')
    ap.add_argument('--no-save-daily', action='store_true', help='不写入 data/daily/<date>.json（回补时建议）')
    return ap.parse_args()


if __name__ == '__main__':
    args = _parse_args()
    # default behavior: if backfilling a past date, do NOT update latest and do NOT overwrite daily json
    now = datetime.now().strftime('%Y-%m-%d')
    is_backfill = bool(args.date and args.date != now)
    update_latest = args.update_latest if not is_backfill else False
    save_daily = False if (args.no_save_daily or is_backfill) else True
    run(date_str=args.date, update_latest=update_latest, save_daily=save_daily)
