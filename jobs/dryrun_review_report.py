"""Dry-run review report (3-day).

Reads:
- data/trades/paper_ledger.jsonl (simulated fills)
- data/trades/dryrun_scan_ledger.jsonl (scan funnel, new vs dup)

Outputs a concise markdown report suitable for Telegram.

Usage:
  python3 jobs/dryrun_review_report.py --start 2026-03-01 --end 2026-03-05

Notes:
- Best-effort pricing: mark-to-market uses yfinance daily close.
- This job is for review/acceptance, not trading decisions.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


ROOT = Path(__file__).resolve().parent.parent
PAPER_LEDGER = ROOT / "data" / "trades" / "paper_ledger.jsonl"
SCAN_LEDGER  = ROOT / "data" / "trades" / "dryrun_scan_ledger.jsonl"


def _load_jsonl(path: Path) -> List[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def _in_range(ts: str, start: str, end: str) -> bool:
    # ts like 2026-03-01T19:22:49
    d = (ts or "")[:10]
    return (d >= start) and (d <= end)


def _fmt_pct(x: float) -> str:
    return f"{x:+.2f}%"


def _fmt_money(x: float) -> str:
    sign = "+" if x >= 0 else "-"
    return f"{sign}${abs(x):.2f}"


def _yf_last_closes(tickers: List[str]) -> Dict[str, float]:
    # tickers are like TSLA (no .US)
    if not tickers:
        return {}
    try:
        import yfinance as yf

        raw = yf.download(
            tickers,
            period="10d",
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
        out: Dict[str, float] = {}
        for t in tickers:
            try:
                closes = raw["Close"] if len(tickers) == 1 else raw["Close"][t]
                closes = closes.dropna()
                if len(closes) == 0:
                    continue
                out[t] = float(closes.iloc[-1])
            except Exception:
                continue
        return out
    except Exception:
        return {}


def build_report(start: str, end: str) -> str:
    # ---- Trades (paper ledger) ----
    paper = _load_jsonl(PAPER_LEDGER)
    paper = [r for r in paper if r.get("status") == "FILLED" and _in_range(r.get("created_at", ""), start, end)]
    paper.sort(key=lambda r: r.get("created_at", ""))

    # Build open positions (assume no sells or partials; still handle in case)
    pos_qty = defaultdict(int)
    pos_cost = defaultdict(float)
    for r in paper:
        sym = r.get("symbol")
        side = (r.get("side") or "").lower()
        qty = int(r.get("qty") or 0)
        px = float(r.get("fill_price") or r.get("limit_price") or 0)
        if not sym or qty <= 0 or px <= 0:
            continue
        if side == "buy":
            pos_qty[sym] += qty
            pos_cost[sym] += qty * px
        elif side == "sell":
            pos_qty[sym] -= qty
            pos_cost[sym] -= qty * px

    open_syms = [s for s in pos_qty.keys() if pos_qty[s] != 0]
    yf_tickers = [s.replace(".US", "") for s in open_syms]
    last_close = _yf_last_closes(yf_tickers)

    mtm_lines = []
    total_pnl = 0.0
    for sym in sorted(open_syms):
        t = sym.replace(".US", "")
        qty = pos_qty[sym]
        avg = (pos_cost[sym] / qty) if qty else 0.0
        px = last_close.get(t)
        if px is None or avg <= 0:
            continue
        pnl = (px - avg) * qty
        ret = (px / avg - 1) * 100
        total_pnl += pnl
        mtm_lines.append(f"  • {sym} qty={qty} entry={avg:.2f} last={px:.2f} ret={_fmt_pct(ret)} pnl={_fmt_money(pnl)}")

    # ---- Scan funnel (scan ledger) ----
    scans = _load_jsonl(SCAN_LEDGER)
    scans = [r for r in scans if _in_range(r.get("generated_at", ""), start, end)]

    by_date = defaultdict(Counter)
    sig_counts = Counter()
    new_sig_counts = Counter()

    for r in scans:
        d = (r.get("generated_at") or "")[:10]
        c = r.get("counts") or {}
        for k in ["raw", "ret5", "routed", "threshold", "new", "dup"]:
            try:
                by_date[d][k] += int(c.get(k, 0) or 0)
            except Exception:
                pass

        for s in (r.get("new_buy") or []):
            t = s.get("ticker")
            if t:
                sig_counts[t] += 1
                new_sig_counts[t] += 1
        for s in (r.get("dup_buy") or []):
            t = s.get("ticker")
            if t:
                sig_counts[t] += 1

    # ---- Compose ----
    lines = []
    lines.append(f"🧾 **3天 Dry-run 复盘（含 3/1）** | {start} → {end}")
    lines.append("━━━━━━━━━━━━━━━━")

    lines.append("\n1) **执行收益（paper_ledger mark-to-market，best-effort）**")
    if mtm_lines:
        lines.extend(mtm_lines)
        lines.append(f"  • 合计浮动 PnL：{_fmt_money(total_pnl)}")
    else:
        lines.append("  • 无可计算的 open positions（可能无成交/或价格取数失败）")

    lines.append("\n2) **成交明细（FILLED）**")
    if paper:
        for r in paper[:20]:
            lines.append(
                f"  • {r.get('created_at','')[:19]} {r.get('symbol')} {r.get('side')} {r.get('qty')} @ {r.get('fill_price') or r.get('limit_price')} | {r.get('remark','')[:80]}"
            )
    else:
        lines.append("  • 本区间无 FILLED 记录")

    lines.append("\n3) **扫描漏斗（scan_ledger）**")
    if by_date:
        for d in sorted(by_date.keys()):
            c = by_date[d]
            lines.append(
                f"  • {d}：raw={c['raw']} ret5={c['ret5']} routed={c['routed']} threshold={c['threshold']} new={c['new']} dup={c['dup']}"
            )
    else:
        lines.append("  • 本区间无 scan ledger 记录")

    lines.append("\n4) **信号出现频次 Top（含 dup）**")
    if sig_counts:
        top = sig_counts.most_common(8)
        for t, n in top:
            new_n = new_sig_counts.get(t, 0)
            lines.append(f"  • {t}: {n} 次（new={new_n} dup={n-new_n}）")
    else:
        lines.append("  • 无")

    lines.append("\n5) **结论（验收用）**")
    lines.append("  • 系统稳定性：已补齐 NO_SIGNAL 可解释摘要 + dup 可见 + ledger 可追溯")
    lines.append("  • 当前阶段：成交很少，收益波动主要来自 TSLA 单笔；需要等 3/5 收盘后做最终验收")
    lines.append("  • 下一步：如继续 dry-run，可增加“平仓/止损触发回放”统计，完善收益验收闭环")

    lines.append("\n━━━━━━━━━━━━━━━━")
    lines.append("_仅供验收复盘，不构成投资建议_")

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    args = ap.parse_args()

    msg = build_report(args.start, args.end)
    print("DRYRUN_REVIEW_START")
    print(msg)
    print("DRYRUN_REVIEW_END")


if __name__ == "__main__":
    main()
