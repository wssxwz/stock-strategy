"""Evaluate an OrderIntent for affordability and ranking."""

from __future__ import annotations

from dataclasses import dataclass

from broker.paper_executor import OrderIntent


@dataclass
class IntentMetrics:
    notional: float
    sl_pct: float
    risk_usd: float
    score: float


def compute_metrics(intent: OrderIntent, *, signal_score: float | None = None) -> IntentMetrics:
    entry = float(intent.limit_price or 0)
    sl = float(intent.sl_price or 0)
    qty = float(intent.qty or 0)

    notional = entry * qty
    sl_pct = (entry - sl) / entry if entry > 0 and sl > 0 else 1.0
    risk_usd = max(0.0, (entry - sl) * qty)

    # execution score: higher signal_score, lower sl_pct, lower notional preferred
    base = float(signal_score or 0)
    score = base - (sl_pct * 50.0) - (notional / 1000.0)

    return IntentMetrics(notional=notional, sl_pct=sl_pct, risk_usd=risk_usd, score=score)
