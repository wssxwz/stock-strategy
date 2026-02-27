"""美股盘前前瞻（北京时间21:00）

定位：短、狠、可执行。
数据：优先使用 yfinance 可拿到的盘前/期货/指数数据。
注意：免费数据源可能存在延迟与字段缺失，脚本需容错。

输出：PREMARKET_START ~ PREMARKET_END
"""

import os, sys, warnings
warnings.filterwarnings('ignore')

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime

import yfinance as yf

# Reuse market_data constants when available
from market_data import get_batch_quotes, INDICES, COMMODITIES


FUTURES = {
    'ES=F': '标普期货(ES)',
    'NQ=F': '纳指期货(NQ)',
    'YM=F': '道指期货(YM)',
    'RTY=F': '罗素期货(RTY)',
}

WATCH_CORE = [
    'NVDA','TSLA','AAPL','MSFT','AMZN','GOOGL','META','AMD','INTC','CRWD','PANW','ORCL',
    'BABA','BIDU','PDD','JD','NIO','LI','BILI','TCOM'
]


def _fmt_pct(p):
    try:
        p = float(p)
    except Exception:
        p = 0.0
    return f"{('+' if p>=0 else '')}{p:.2f}%"


def _get_last_change_pct(symbol: str):
    """Return change% using last two closes (best-effort)."""
    try:
        h = yf.Ticker(symbol).history(period='2d', interval='1d', auto_adjust=True)
        if h is None or h.empty or len(h) < 2:
            return None
        c0 = float(h['Close'].iloc[-2])
        c1 = float(h['Close'].iloc[-1])
        if c0 == 0:
            return None
        return (c1 / c0 - 1) * 100
    except Exception:
        return None


def _get_premarket_quote(symbol: str):
    """Try to fetch premarket price and change% (best-effort)."""
    try:
        # 1m data with prepost often works during premarket; otherwise fallback to info
        h = yf.download(symbol, period='1d', interval='1m', prepost=True, auto_adjust=True, progress=False, threads=False)
        if h is not None and not h.empty:
            px = float(h['Close'].iloc[-1])
            # change vs last regular close (approx from daily)
            chg = _get_last_change_pct(symbol)
            return px, chg
    except Exception:
        pass

    try:
        info = yf.Ticker(symbol).fast_info
        px = info.get('lastPrice', None)
        return (float(px) if px else None), _get_last_change_pct(symbol)
    except Exception:
        return None, _get_last_change_pct(symbol)


def run():
    now = datetime.now()
    date_str = now.strftime('%-m月%-d日') if hasattr(now, 'strftime') else now.strftime('%m月%d日')

    # Futures (best-effort)
    fut_lines = []
    for s, name in FUTURES.items():
        pct = _get_last_change_pct(s)
        if pct is None:
            continue
        fut_lines.append(f"• {name} {_fmt_pct(pct)}")

    # Indices snapshot (from existing market_data, may reflect last close)
    idx = get_batch_quotes(list(INDICES.keys()))

    # Core movers (premarket quote best-effort)
    movers = []
    for t in WATCH_CORE:
        px, pct = _get_premarket_quote(t)
        if pct is None and px is None:
            continue
        movers.append((t, pct if pct is not None else 0.0, px))

    # pick top up/down by pct
    movers_sorted = sorted(movers, key=lambda x: x[1], reverse=True)
    top_up = [m for m in movers_sorted[:5] if m[1] is not None]
    top_dn = [m for m in sorted(movers, key=lambda x: x[1])[:5] if m[1] is not None]

    # Commodities
    cmd = get_batch_quotes(list(COMMODITIES.keys()))

    lines = [
        f"{date_str} 美股前瞻",
        "一、大盘整体走势",
    ]

    if fut_lines:
        lines.append("• 期指概览：" + "；".join([l.replace('• ','') for l in fut_lines[:3]]))
    else:
        # fallback to last close
        try:
            spy = idx.get('SPY', {}).get('change_pct', 0)
            qqq = idx.get('QQQ', {}).get('change_pct', 0)
            dia = idx.get('DIA', {}).get('change_pct', 0)
            lines.append(f"• 参考昨夜：SPY {_fmt_pct(spy)}｜QQQ {_fmt_pct(qqq)}｜DIA {_fmt_pct(dia)}")
        except Exception:
            pass

    lines.append("\n二、热门板块与个股表现")
    if top_up:
        up_txt = '；'.join([f"{t} {_fmt_pct(pct)}" for t,pct,_ in top_up[:3]])
        lines.append(f"• 盘前相对强势：{up_txt}")
    if top_dn:
        dn_txt = '；'.join([f"{t} {_fmt_pct(pct)}" for t,pct,_ in top_dn[:3]])
        lines.append(f"• 盘前相对承压：{dn_txt}")

    lines.append("\n三、核心个股动态")
    lines.append("• 建议关注：NVDA/TSLA/GOOGL/META（强波动时优先看龙头定方向）")

    lines.append("\n四、全球宏观与行业趋势")
    # keep it short; data-limited
    vix = idx.get('VIX', {}).get('price', None)
    if vix is not None:
        lines.append(f"• 波动率：VIX {vix}（>20 注意止损纪律）")

    if cmd:
        try:
            oil = cmd.get('CL=F', {}).get('change_pct', None)
            gold = cmd.get('GC=F', {}).get('change_pct', None)
            if oil is not None or gold is not None:
                seg=[]
                if oil is not None: seg.append(f"原油{_fmt_pct(oil)}")
                if gold is not None: seg.append(f"黄金{_fmt_pct(gold)}")
                lines.append("• 大宗：" + '｜'.join(seg))
        except Exception:
            pass

    lines.append("\n五、盘前关注清单（最少三件事）")
    lines.append("• 1）开盘前 30 分钟：期指方向是否反转")
    lines.append("• 2）龙头股是否带量（NVDA/TSLA/QQQ）")
    lines.append("• 3）若高波动（VIX偏高），优先小仓试错")

    lines.append("\n六、宏观事历提醒（北京时间）")
    lines.append("• 21:30 开盘前后是波动放大窗口（关注数据/财报）")

    msg = '\n'.join(lines)

    print('PREMARKET_START')
    print(msg)
    print('PREMARKET_END')


if __name__ == '__main__':
    run()
