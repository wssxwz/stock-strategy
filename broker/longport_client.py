"""LongPort client wrapper.

Safety: provides contexts and quote helpers only.
Order submission should happen in executor with explicit mode.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from longport.openapi import Config, QuoteContext, TradeContext


@dataclass
class QuoteSnapshot:
    symbol: str
    last: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    ts: Optional[datetime] = None


def load_config() -> Config:
    return Config.from_env()


def make_quote_ctx(config: Config | None = None) -> QuoteContext:
    return QuoteContext(config or load_config())


def make_trade_ctx(config: Config | None = None) -> TradeContext:
    return TradeContext(config or load_config())


def get_quote(ctx: QuoteContext, symbol: str) -> QuoteSnapshot:
    """Best-effort quote snapshot.

    SDK returns typed objects; we defensively parse expected fields.
    """
    resp = ctx.quote([symbol])
    if not resp:
        return QuoteSnapshot(symbol=symbol, ts=datetime.now(timezone.utc))

    q = resp[0]

    def g(obj, name, default=None):
        return getattr(obj, name, default)

    last = g(q, 'last_done', None)
    bid = g(q, 'bid_price', None)
    ask = g(q, 'ask_price', None)

    def f(x):
        if x is None:
            return None
        try:
            return float(x)
        except Exception:
            return None

    return QuoteSnapshot(
        symbol=symbol,
        last=f(last),
        bid=f(bid),
        ask=f(ask),
        ts=datetime.now(timezone.utc),
    )
