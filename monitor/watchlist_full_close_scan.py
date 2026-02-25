"""One-shot scan for WATCHLIST_FULL using yesterday close baseline.

- Phase1: daily filter (3mo, 1d)
- Phase2: 1h scoring on the last 1h bar of the most recent completed trading day.
- Output: grouped MR vs STRUCT and deduped tickers.

This script is intended for ad-hoc operator runs (quiet output).
"""

import os, sys, io
from datetime import datetime
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../src'))

from fast_scan import phase1_filter
from analyzer.indicators import add_all_indicators
from signal_engine import score_signal, _structure_signals
from data_store import sync_and_load
import config as cfg


def _pick_baseline_row(df: pd.DataFrame):
    """Pick baseline = last bar of the latest trading date in df."""
    last_date = pd.to_datetime(df.index.max()).date()
    day_df = df[df.index.date == last_date]
    if day_df.empty:
        return None, None
    return day_df.index[-1], day_df.iloc[-1]


def run_scan(watchlist=None, min_score=None):
    watchlist = watchlist or cfg.WATCHLIST_FULL
    notify = cfg.NOTIFY
    min_score = min_score if min_score is not None else notify.get('min_score', 70)

    candidates = phase1_filter(watchlist)

    rows = []
    errs = 0
    base_date = None

    for c in candidates:
        t = c['ticker']
        try:
            df = sync_and_load(t, interval='1h', lookback_days=120, max_auto_lookback_days=730)
            if df is None or df.empty or len(df) < 50:
                continue

            df = df.copy()
            df.columns = [x.lower() for x in df.columns]
            if 'rsi14' not in df.columns:
                df = add_all_indicators(df)

            bar_time, row = _pick_baseline_row(df)
            if row is None:
                continue

            if base_date is None:
                base_date = str(pd.to_datetime(bar_time).date())

            sig = score_signal(row, t)
            sig['ticker'] = t
            sig['bar_time'] = bar_time.strftime('%Y-%m-%d %H:%M')
            sig['price'] = round(float(row.get('close', sig.get('price', 0))), 2)

            ss = _structure_signals(df.loc[:bar_time], t)
            mr_ok = float(sig.get('score', 0) or 0) >= float(min_score)
            has_struct = bool(ss.get('signals'))

            if mr_ok or has_struct:
                rows.append({
                    'ticker': t,
                    'price': sig['price'],
                    'bar_time': sig['bar_time'],
                    'mr_score': int(sig.get('score', 0) or 0),
                    'mr_ok': bool(mr_ok),
                    'struct_types': ','.join([s.get('type', '') for s in (ss.get('signals') or [])]),
                    'best_struct': (ss.get('best') or {}).get('type') if ss.get('best') else '',
                })
        except Exception:
            errs += 1

    out = pd.DataFrame(rows)
    if out.empty:
        return {
            'base_date': base_date,
            'candidates': len(candidates),
            'errs': errs,
            'out': out,
        }

    # Deduplicate by ticker: keep the highest priority row (MR ok first, then higher score)
    out = out.sort_values(by=['mr_ok', 'mr_score', 'ticker'], ascending=[False, False, True])
    out = out.drop_duplicates(subset=['ticker'], keep='first').reset_index(drop=True)

    return {
        'base_date': base_date,
        'candidates': len(candidates),
        'errs': errs,
        'out': out,
    }


def main():
    res = run_scan()
    out = res['out']

    os.makedirs(os.path.join(os.path.dirname(__file__), '../data/tmp'), exist_ok=True)
    stamp = res['base_date'] or datetime.now().strftime('%Y-%m-%d')
    path = os.path.join(os.path.dirname(__file__), f"../data/tmp/watchlist_full_opportunities_{stamp}-close.csv")
    if out is not None and not out.empty:
        out.to_csv(path, index=False)

    print(f"Base close date: {res['base_date']} | Candidates: {res['candidates']} | Opportunities: {0 if out is None else len(out)} | errs: {res['errs']}")
    if out is None or out.empty:
        return

    mr = out[out['mr_ok'] == True].copy()
    st = out[(out['mr_ok'] == False) & (out['best_struct'] != '')].copy()

    if not mr.empty:
        print("\n[MR opportunities]")
        for _, r in mr.iterrows():
            print(f"{r['ticker']:<6} ${r['price']:<8} @ {r['bar_time']}  |  MR {int(r['mr_score'])}")

    if not st.empty:
        print("\n[STRUCT-only opportunities]")
        for _, r in st.iterrows():
            print(f"{r['ticker']:<6} ${r['price']:<8} @ {r['bar_time']}  |  STRUCT {r['best_struct']}")

    print(f"\nSaved: {path}")


if __name__ == '__main__':
    main()
