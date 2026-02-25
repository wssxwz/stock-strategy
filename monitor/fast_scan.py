"""
两阶段扫描器
第一阶段：批量拉日线，快速过滤（几秒/只）
第二阶段：只对候选标的拉1h数据，精细评分（几秒/只）
整体目标：501只 → 5分钟内完成
"""
import sys, os, warnings, json
warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../src'))

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import io
import contextlib
import logging

# reduce yfinance noise
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# local parquet store
try:
    from data_store import sync_and_load
except Exception:
    sync_and_load = None
from analyzer.indicators import add_all_indicators
from signal_engine import score_signal, check_stabilization, format_signal_message
from config import WATCHLIST, NOTIFY

STATE_FILE = os.path.join(os.path.dirname(__file__), '.monitor_state.json')

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {'sent_signals': {}}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2, default=str)

def signal_key(sig):
    date_str = datetime.now().strftime('%Y-%m-%d')
    return f"{sig['ticker']}_{date_str}_{sig['score']//10*10}"

# ── 第一阶段：批量拉日线快速过滤 ──
def phase1_filter(tickers: list, batch_size: int = 100) -> list:
    """
    批量下载日线，过滤出可能触发买入信号的候选股
    条件（宽松）：RSI<55 AND BB%<0.5 AND 距52周高点>-5%
    """
    candidates = []
    total = len(tickers)
    print(f"  第一阶段：快速过滤 {total} 只股票（日线批量下载）")

    for i in range(0, total, batch_size):
        batch = tickers[i:i+batch_size]
        raw = None
        try:
            # yfinance sometimes prints noisy errors; silence stdout/stderr here
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                raw = yf.download(
                    batch, period='3mo', interval='1d',
                    auto_adjust=True, group_by='ticker',
                    progress=False, threads=True
                )
        except Exception as e:
            print(f"    批次 {i//batch_size+1} 批量下载失败: {e}（将逐只重试）")

        def _download_one(tk: str) -> pd.DataFrame:
            """Per-ticker fallback download to avoid batch-level failures and reduce spam."""
            try:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    df1 = yf.Ticker(tk).history(period='3mo', interval='1d', auto_adjust=True)
                if df1 is None:
                    return pd.DataFrame()
                return df1
            except Exception:
                return pd.DataFrame()

        for ticker in batch:
            try:
                if raw is None:
                    df = _download_one(ticker)
                else:
                    if len(batch) == 1:
                        df = raw.copy()
                    else:
                        try:
                            df = raw[ticker].copy() if ticker in raw.columns.get_level_values(0) else pd.DataFrame()
                        except Exception:
                            df = pd.DataFrame()
                    if df is None or df.empty:
                        df = _download_one(ticker)

                if df is None or df.empty or len(df) < 20:
                    continue

                df.columns = [c.lower() for c in df.columns]
                df = df.dropna(subset=['close'])

                # 简单指标
                close = df['close']
                rsi_gain = close.diff().clip(lower=0).rolling(14).mean()
                rsi_loss = (-close.diff()).clip(lower=0).rolling(14).mean()
                rsi = 100 - 100 / (1 + rsi_gain / rsi_loss.replace(0, 1e-9))
                latest_rsi = rsi.iloc[-1]

                ma20 = close.rolling(20).mean().iloc[-1]
                std20 = close.rolling(20).std().iloc[-1]
                latest_close = close.iloc[-1]
                bb_pct = (latest_close - (ma20 - 2*std20)) / (4*std20) if std20 > 0 else 0.5

                ret_5d = (latest_close / close.iloc[-5] - 1) * 100 if len(close) >= 5 else 0

                # 宽松过滤：RSI<58 + BB%<0.55 + 近期有回调
                if latest_rsi < 58 and bb_pct < 0.55 and ret_5d < 5:
                    candidates.append({
                        'ticker': ticker,
                        'rsi_d': round(latest_rsi, 1),
                        'bb_d':  round(bb_pct, 3),
                        'ret5d': round(ret_5d, 1),
                        'price': round(latest_close, 2),
                    })
            except Exception:
                continue

        done = min(i+batch_size, total)
        print(f"    进度: {done}/{total}  候选: {len(candidates)}只")

    print(f"  ✅ 第一阶段完成，候选: {len(candidates)} 只")
    return candidates


# ── 第二阶段：1h精细评分 ──
def phase2_score(candidates: list) -> list:
    """对候选标的拉1h数据，精细评分"""
    signals = []
    print(f"\n  第二阶段：精细评分 {len(candidates)} 只候选标的（1h数据）")

    for c in candidates:
        ticker = c['ticker']
        try:
            end = datetime.now()
            start = end - timedelta(days=59)
            # 注意：yfinance 的 end 是“非包含”，用 +1 天避免漏掉当天盘中数据
            if sync_and_load is not None:
                df = sync_and_load(ticker, interval='1h', lookback_days=120)
            else:
                df = yf.Ticker(ticker).history(
                    start=start.strftime('%Y-%m-%d'),
                    end=(end + timedelta(days=1)).strftime('%Y-%m-%d'),
                    interval='1h', auto_adjust=True
                )
            if len(df) < 30:
                continue

            df.index = df.index.tz_localize(None) if df.index.tzinfo else df.index
            df.columns = [c2.lower() for c2 in df.columns]
            df = add_all_indicators(df)

            # 用“信号触发那根 1H K线的收盘价”作为价格口径（可复现）
            row = df.iloc[-1]
            sig = score_signal(row, ticker)

            # Structure signals (1buy/2buy) — grey mode: compute & attach only
            try:
                from signal_engine import _structure_signals
                ss = _structure_signals(df, ticker)
                sig['structure'] = ss
            except Exception:
                sig['structure'] = {'enabled': False, 'signals': [], 'best': None}
            sig['bar_time']  = df.index[-1].strftime('%Y-%m-%d %H:%M')
            sig['bar_close'] = round(float(row.get('close')), 2) if 'close' in row else sig.get('price')
            sig['price'] = sig['bar_close']  # 统一口径：当前价=触发bar的收盘价

            # ── P0: 企稳确认（有完整 df，做全量检查）────────────
            stab = check_stabilization(df)
            sig['score'] = min(100, sig['score'] + stab['score_bonus'])
            sig['stabilization'] = stab
            # 把企稳信号插入 details 最前面
            sig['details'] = stab['signals'] + sig.get('details', [])

            status = f"    {ticker:<6} 评分={sig['score']:>3}  RSI={sig['rsi14']:>5.1f}  BB%={sig['bb_pct']:>6.3f}  MA200={'✅' if sig['above_ma200'] else '❌'}  企稳={'✅' if stab['confirmed'] else '⚠️'}"
            if sig['score'] >= NOTIFY['min_score']:
                status += f"  ← 🔔 信号触发!"
            print(status)

            if sig['score'] >= NOTIFY['min_score']:
                signals.append(sig)

        except Exception as e:
            print(f"    {ticker}: ✗ {e}")

    return signals


def run_fast_scan(watchlist=None):
    if watchlist is None:
        watchlist = WATCHLIST

    print(f"\n{'='*60}")
    print(f"🔍 股票信号扫描  {datetime.now().strftime('%Y-%m-%d %H:%M')} (北京时间)")
    print(f"   股票池: {len(watchlist)} 只  |  信号阈值: ≥{NOTIFY['min_score']}分")
    print(f"{'='*60}")

    t0 = datetime.now()

    # 第一阶段快速过滤
    candidates = phase1_filter(watchlist)

    if not candidates:
        print("\n❌ 无候选标的，跳过第二阶段")
        return []

    # 第二阶段精细评分
    signals = phase2_score(candidates)

    elapsed = (datetime.now() - t0).seconds
    print(f"\n  ⏱️ 总耗时: {elapsed}秒  |  触发信号: {len(signals)} 只")

    return signals


if __name__ == '__main__':
    state = load_state()
    signals = run_fast_scan()

    new_signals = []
    for sig in signals:
        key = signal_key(sig)
        if key not in state['sent_signals']:
            new_signals.append(sig)
            state['sent_signals'][key] = {
                'ticker': sig['ticker'], 'score': sig['score'],
                'price': sig['price'], 'time': datetime.now().isoformat()
            }

    if new_signals:
        print(f"\n{'='*60}")
        print(f"📨 新信号 ({len(new_signals)} 只):")
        for sig in new_signals:
            msg = format_signal_message(sig)
            print(f"\nSIGNAL:{sig['ticker']}:{sig['score']}")
            print(msg)
            print("---END---")
    else:
        print("\nNO_SIGNAL")

    save_state(state)
