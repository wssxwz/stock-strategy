"""Exit monitor based on local open_positions state (preferred for automated trading).

This avoids relying on manual portfolio.json.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ExitEvent:
    symbol: str
    kind: str  # STOP_LOSS / TAKE_PROFIT
    last: float
    entry: float
    sl: Optional[float]
    tp: Optional[float]


def check_open_positions(open_positions: dict, quotes: dict) -> List[ExitEvent]:
    events: List[ExitEvent] = []
    for sym, rec in (open_positions or {}).items():
        try:
            entry = float(rec.get('entry') or 0)
            sl = rec.get('sl')
            tp = rec.get('tp')
            sl_f = float(sl) if sl is not None else None
            tp_f = float(tp) if tp is not None else None
            last = float(quotes.get(sym) or 0)
        except Exception:
            continue

        if last <= 0 or entry <= 0:
            continue

        if sl_f is not None and last <= sl_f:
            events.append(ExitEvent(symbol=sym, kind='STOP_LOSS', last=last, entry=entry, sl=sl_f, tp=tp_f))
        elif tp_f is not None and last >= tp_f:
            events.append(ExitEvent(symbol=sym, kind='TAKE_PROFIT', last=last, entry=entry, sl=sl_f, tp=tp_f))

    return events
