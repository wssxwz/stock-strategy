"""Trading environment and safety guards.

We support two environments:
- paper: safe default
- live: requires explicit confirmation flag

Never store secrets in repo; all credentials are loaded from env.
"""

from __future__ import annotations

import os


def trading_env() -> str:
    return (os.environ.get('TRADING_ENV') or 'paper').strip().lower()


def is_paper() -> bool:
    return trading_env() == 'paper'


def is_live() -> bool:
    return trading_env() == 'live'


def live_trading_enabled() -> bool:
    # hard guard to prevent accidental live trading
    v = (os.environ.get('LIVE_TRADING') or '').strip().upper()
    return v in {'YES', 'TRUE', '1', 'YES_I_KNOW'}


def require_paper_for_paper_executor():
    if not is_paper():
        raise RuntimeError('paper executor blocked: TRADING_ENV is not paper')


def require_live_enabled():
    if not is_live() or not live_trading_enabled():
        raise RuntimeError('live trading blocked: set TRADING_ENV=live and LIVE_TRADING=YES_I_KNOW')
