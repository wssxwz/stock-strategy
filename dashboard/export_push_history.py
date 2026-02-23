"""把 signals.json 导出为 push_history.json（用于 Dashboard 推送历史展示 / 开放平台）

说明：
- 当前 Telegram 推送来自扫描程序的格式化文本，但 Dashboard 本身只存 signals.json
- 这里把 signals.json 的每条信号转成统一的 push_history 记录（id/time/title/content）
- 以后如果要做到“完全同步 Telegram 推送原文”，可以在 monitor 侧直接写入 push_history.json
"""

import json
import os
from datetime import datetime

BASE = os.path.dirname(__file__)
SIGNALS = os.path.join(BASE, 'signals.json')
OUT_DASH = os.path.join(BASE, 'push_history.json')
OUT_ROOT = os.path.join(BASE, '..', 'push_history.json')


def build_content(sig: dict) -> str:
    # 用 signals.json 字段拼一个“平台可读”的摘要
    ticker = sig.get('ticker','')
    score  = sig.get('score','')
    price  = sig.get('price','')
    rsi    = sig.get('rsi14','')
    bb     = sig.get('bb_pct','')
    tp     = sig.get('tp_price','')
    sl     = sig.get('sl_price','')
    kb     = sig.get('kb_tag','')

    lines = [
        f"{kb}📊 评分: {score}/100",
        f"💰 当前价: ${price}",
        f"📈 RSI14: {rsi}  |  BB%: {bb}",
        f"🎯 止盈: ${tp}  |  🛡️ 止损: ${sl}",
    ]
    return "\n".join(lines)


def load_hist(path: str):
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_hist(hist: list):
    for path in [OUT_DASH, OUT_ROOT]:
        with open(path, 'w') as f:
            json.dump(hist, f, ensure_ascii=False, indent=2)


def append_push_history(type_: str, title: str, summary: str, raw: str, time: str = None):
    """追加一条推送历史（供 monitor 侧调用）"""
    hist = load_hist(OUT_DASH)
    if not isinstance(hist, list):
        hist = []

    rid = f"ph_{datetime.now().timestamp()}"
    item = {
        'id': rid,
        'type': type_,
        'title': title,
        'summary': summary,
        'content': summary,
        'raw': raw,
        'time': time or datetime.now().strftime('%Y-%m-%d %H:%M'),
    }
    hist.insert(0, item)
    if len(hist) > 800:
        hist = hist[:800]
    save_hist(hist)
    return item


def run():
    """从 signals.json 重建 push_history（摘要版）"""
    if not os.path.exists(SIGNALS):
        data = []
    else:
        with open(SIGNALS, 'r') as f:
            data = json.load(f)

    hist = []
    for s in data:
        t = s.get('time') or ''
        ticker = s.get('ticker','')
        score = s.get('score','')
        title = f"买入信号 {ticker} ({score})"
        summary = build_content(s)
        hist.append({
            'id': s.get('id') or f"hist_{ticker}_{t}",
            'type': 'buy_signal',
            'title': title,
            'summary': summary,
            'content': summary,
            'raw': None,
            'time': t,
        })

    hist = list(reversed(hist))
    save_hist(hist)
    print(f"✅ push_history 已生成: {len(hist)}")


if __name__ == '__main__':
    run()
