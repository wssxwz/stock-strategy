"""Backfill dashboard/signals.json with missing indicator fields.

We historically stored only a subset (rsi14/bb_pct). This script attempts to
reconstruct indicator fields at the signal bar time using local 1h store.

Safe: keeps existing fields, only fills missing.

Usage:
  cd ~/work/stock-strategy && source venv/bin/activate
  python3 jobs/backfill_signals_fields.py

It writes BOTH:
  - dashboard/signals.json
  - signals.json (root)
"""

import os, json
from datetime import datetime

import pandas as pd

# local store
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from data_store import sync_and_load
from analyzer.indicators import add_all_indicators


SIGNALS_DASH = os.path.join(os.path.dirname(__file__), '..', 'dashboard', 'signals.json')
SIGNALS_ROOT = os.path.join(os.path.dirname(__file__), '..', 'signals.json')


def _parse_ts(s: str):
    if not s:
        return None
    try:
        return pd.Timestamp(s)
    except Exception:
        return None


def _pick_row(df: pd.DataFrame, ts: pd.Timestamp):
    if ts in df.index:
        return df.loc[ts], ts
    df2 = df[df.index <= ts]
    if df2.empty:
        return None, None
    return df2.iloc[-1], df2.index[-1]


def _fill_from_row(sig: dict, row: pd.Series):
    # mirror signal_engine fields/units
    def getf(k, default=None):
        v = row.get(k, default)
        try:
            if v is None:
                return default
            if isinstance(v, (bool, int)):
                return bool(v)
        except Exception:
            pass
        return v

    # indicators
    sig.setdefault('schema_version', 2)

    if sig.get('rsi14') is None and 'rsi14' in row:
        sig['rsi14'] = round(float(row.get('rsi14')), 1)
    if sig.get('bb_pct') is None and 'bb_pct20' in row:
        sig['bb_pct'] = round(float(row.get('bb_pct20')), 3)

    if sig.get('macd_hist') is None and 'macd_hist' in row:
        sig['macd_hist'] = round(float(row.get('macd_hist')), 4)
    if sig.get('vol_ratio') is None and 'vol_ratio' in row:
        sig['vol_ratio'] = round(float(row.get('vol_ratio')), 2)

    if sig.get('ret_5d') is None and 'ret_5d' in row:
        sig['ret_5d'] = round(float(row.get('ret_5d')) * 100, 1)

    if sig.get('atr_pct14') is None and 'atr_pct14' in row:
        sig['atr_pct14'] = round(float(row.get('atr_pct14')) * 100, 2)

    if sig.get('above_ma200') is None and 'above_ma200' in row:
        sig['above_ma200'] = bool(int(row.get('above_ma200')))
    if sig.get('above_ma50') is None and 'above_ma50' in row:
        sig['above_ma50'] = bool(int(row.get('above_ma50')))

    # keep price_source if missing
    sig.setdefault('price_source', '1H_bar_close')

    return sig


def main():
    signals = json.load(open(SIGNALS_DASH)) if os.path.exists(SIGNALS_DASH) else []

    # build list of buy signals
    buys = [s for s in signals if s.get('type') == 'buy' and s.get('ticker') and s.get('ticker') != 'TEST']

    cache = {}
    updated = 0
    missed = 0

    for s in buys:
        t = s.get('ticker')
        ts = _parse_ts(s.get('bar_time') or s.get('time'))
        if ts is None:
            missed += 1
            continue

        if t not in cache:
            try:
                df = sync_and_load(t, interval='1h', lookback_days=180, max_auto_lookback_days=730)
                if df is None or df.empty:
                    raise RuntimeError('no df')
                df = df.copy()
                df.columns = [c.lower() for c in df.columns]
                df = add_all_indicators(df) if 'rsi14' not in df.columns else df
                cache[t] = df
            except Exception:
                cache[t] = None

        df = cache.get(t)
        if df is None:
            missed += 1
            continue

        row, used_ts = _pick_row(df, ts)
        if row is None:
            missed += 1
            continue

        before = json.dumps({k: s.get(k) for k in ['macd_hist','vol_ratio','ret_5d','above_ma200','above_ma50','schema_version']}, sort_keys=True)
        _fill_from_row(s, row)
        # update bar_time to the actual used bar
        if s.get('bar_time') is None:
            s['bar_time'] = used_ts.strftime('%Y-%m-%d %H:%M')
        after = json.dumps({k: s.get(k) for k in ['macd_hist','vol_ratio','ret_5d','above_ma200','above_ma50','schema_version']}, sort_keys=True)
        if before != after:
            updated += 1

    # write back
    with open(SIGNALS_DASH, 'w') as f:
        json.dump(signals, f, indent=2, default=str)

    # also keep root copy consistent for Pages
    with open(SIGNALS_ROOT, 'w') as f:
        json.dump(signals, f, indent=2, default=str)

    print(f"Backfill done: updated={updated} missed={missed} total={len(buys)}")


if __name__ == '__main__':
    main()
