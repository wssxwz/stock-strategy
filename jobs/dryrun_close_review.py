"""Post-close dry-run review (3-day observation).

Reads local trading state (gitignored) and produces a concise summary.
Safe: no trading.

Usage:
  source ~/.secrets/env/stock-strategy.live.env
  source venv/bin/activate
  python3 jobs/dryrun_close_review.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from broker.state_store import load_state
from broker.account import get_available_cash


def main():
    st = load_state()
    now = datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M')

    open_pos = st.get('open_positions') or {}
    pending = st.get('pending_orders') or {}
    cooldowns = st.get('cooldowns') or {}
    last_skip = st.get('last_exec_skip') or {}

    usd_cash = None
    try:
        usd_cash = get_available_cash('USD')
    except Exception:
        usd_cash = None

    lines = []
    lines.append(f"🧾 观察期收盘复核（{now} 本地）")
    if usd_cash is not None:
        lines.append(f"• USD 可用现金: {usd_cash:.2f}")

    lines.append(f"• open_positions: {len(open_pos)}")
    lines.append(f"• pending_orders: {len(pending)}")
    lines.append(f"• cooldowns: {len(cooldowns)}")

    if last_skip:
        ts = last_skip.get('ts')
        skipped = last_skip.get('skipped')
        reasons = last_skip.get('reasons') or []
        lines.append(f"\n📌 最近一次执行过滤（ts={ts}）")
        lines.append(f"• skipped={skipped} reasons={len(reasons)}")
        for r in reasons[:6]:
            lines.append(f"  - {r.get('reason')}: {r.get('count')} (e.g. {','.join(r.get('samples') or [])})")

    # quick tuning hints
    hints = []
    if last_skip and any((x.get('reason') or '').startswith('SKIP_HIGH_PRICE') for x in (last_skip.get('reasons') or [])):
        hints.append('高价过滤较多：若机会被错杀，可把 MAX_PRICE_PCT_EQUITY 从 0.35 放宽到 0.40（仍保守）。')
    if last_skip and any((x.get('reason') or '').startswith('SKIP_PRICE_DRIFT') or (x.get('reason') or '').startswith('SKIP_DOUBLE_QUOTE_DRIFT') for x in (last_skip.get('reasons') or [])):
        hints.append('价格漂移较多：考虑放宽 DRIFT 阈值或提高可成交限价 aggressiveness；也可能是行情波动大，应减少开仓。')
    if last_skip and any((x.get('reason') or '').startswith('SKIP_CASH_BUFFER') for x in (last_skip.get('reasons') or [])):
        hints.append('现金 buffer 卡住：可将 MIN_CASH_BUFFER_USD 从 50 下调至 30（不建议更低）。')
    if last_skip and any((x.get('reason') or '').startswith('SKIP_LOW_PRICE_LOW_LIQUIDITY') for x in (last_skip.get('reasons') or [])):
        hints.append('低价低流动性过滤出现：说明方案3在工作，正常。若过严可把 MIN_DOLLAR_VOL_20D 从 20M 下调至 10M。')

    if hints:
        lines.append('\n🛠️ 调参建议（仅供参考）')
        for h in hints[:4]:
            lines.append(f"• {h}")

    msg = '\n'.join(lines)
    print(msg)


if __name__ == '__main__':
    main()
