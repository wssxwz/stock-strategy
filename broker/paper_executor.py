"""Paper trading executor.

Stores intents and simulated fills into a local ledger file.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional


LEDGER_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'trades', 'paper_ledger.jsonl')


@dataclass
class OrderIntent:
    created_at: str
    symbol: str
    side: str
    qty: int
    order_type: str  # LO/MO
    limit_price: Optional[float]
    sl_price: Optional[float]
    tp_price: Optional[float]
    remark: str
    source: dict


def append_ledger(intent: OrderIntent, fill_price: Optional[float] = None, status: str = 'PENDING'):
    os.makedirs(os.path.dirname(LEDGER_PATH), exist_ok=True)
    rec = {
        **asdict(intent),
        'status': status,
        'fill_price': fill_price,
        'updated_at': datetime.now().isoformat(timespec='seconds'),
    }
    with open(LEDGER_PATH, 'a') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')


def make_intent(**kwargs) -> OrderIntent:
    return OrderIntent(created_at=datetime.now().isoformat(timespec='seconds'), **kwargs)
