"""Live trading executor via LongPort Trade API.

Safety model:
- Hard-gated by env flags in broker.trading_env
- Default behavior is DRY_RUN unless explicitly enabled

This module is *only* used when:
  TRADING_ENV=live
  LIVE_TRADING=YES_I_KNOW

Even then, you can keep DRY_RUN by setting LIVE_SUBMIT=0.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from longport.openapi import TradeContext, OrderType, OrderSide, TimeInForceType

from broker.longport_client import load_config, make_trade_ctx
from broker.paper_executor import OrderIntent
from broker.trading_env import require_live_enabled


@dataclass
class LiveSubmitResult:
    ok: bool
    dry_run: bool
    order_id: Optional[str] = None
    error: Optional[str] = None


def submit_live_order(intent: OrderIntent, *, dry_run: bool = True) -> LiveSubmitResult:
    """Submit a live order (or dry-run).

    We use limit order (LO) + Day by default.
    """
    require_live_enabled()

    if dry_run:
        # synthetic id to exercise the tracking pipeline
        oid = f"DRYRUN-{intent.symbol}-{intent.side}-{intent.created_at}"
        return LiveSubmitResult(ok=True, dry_run=True, order_id=oid)

    try:
        cfg = load_config()
        tctx: TradeContext = make_trade_ctx(cfg)

        side = OrderSide.Buy if intent.side.lower() == 'buy' else OrderSide.Sell

        if intent.order_type.upper() != 'LO':
            return LiveSubmitResult(ok=False, dry_run=False, error=f"unsupported order_type={intent.order_type}")
        if intent.limit_price is None:
            return LiveSubmitResult(ok=False, dry_run=False, error='missing limit_price')

        resp = tctx.submit_order(
            intent.symbol,
            OrderType.LO,
            side,
            Decimal(str(intent.qty)),
            TimeInForceType.Day,
            submitted_price=Decimal(str(intent.limit_price)),
            remark=intent.remark[:64],
        )

        # resp has order_id field in docs
        order_id = getattr(resp, 'order_id', None)
        return LiveSubmitResult(ok=True, dry_run=False, order_id=str(order_id) if order_id is not None else None)

    except Exception as e:
        return LiveSubmitResult(ok=False, dry_run=False, error=str(e))
