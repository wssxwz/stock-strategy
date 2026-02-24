"""Local OHLCV data store (Parquet)

Goal
- Persist 1H/1D market data locally so the system is not limited by yfinance's rolling windows.
- Make scans/backtests fast and reproducible.

Storage
- data/store/{interval}/{TICKER}.parquet
  - interval: "1h" or "1d"
  - columns: open, high, low, close, volume (+ optional dividends/splits)
  - index: naive timestamp (tz removed)

Design choices
- Append-only with de-dup by index.
- Sync fetches a sliding calendar window (default 60d) and merges.
- For 1H, yfinance only offers ~730d rolling, but by running sync daily we can accumulate >2y.

Usage
  from data_store import load_local, sync_and_load
  df = sync_and_load('TSLA', interval='1h', lookback_days=60)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import yfinance as yf


@dataclass
class StoreConfig:
    base_dir: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "store")


def _path(cfg: StoreConfig, ticker: str, interval: str) -> str:
    interval = interval.lower()
    if interval not in {"1h", "1d"}:
        raise ValueError(f"unsupported interval: {interval}")
    d = os.path.join(cfg.base_dir, interval)
    os.makedirs(d, exist_ok=True)
    safe = ticker.replace("/", "_").replace(":", "_")
    return os.path.join(d, f"{safe}.parquet")


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.dropna().copy()
    # remove tz for stable joins
    try:
        out.index = out.index.tz_convert(None)
    except Exception:
        try:
            out.index = out.index.tz_localize(None)
        except Exception:
            pass
    out.columns = [c.lower() for c in out.columns]
    out = out[~out.index.duplicated(keep="last")]
    out = out.sort_index()
    return out


def load_local(ticker: str, interval: str = "1h", cfg: Optional[StoreConfig] = None) -> pd.DataFrame:
    cfg = cfg or StoreConfig()
    p = _path(cfg, ticker, interval)
    if not os.path.exists(p):
        return pd.DataFrame()
    df = pd.read_parquet(p)
    if "index" in df.columns and not isinstance(df.index, pd.DatetimeIndex):
        df = df.set_index("index")
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    return df


def save_local(ticker: str, df: pd.DataFrame, interval: str = "1h", cfg: Optional[StoreConfig] = None) -> None:
    cfg = cfg or StoreConfig()
    p = _path(cfg, ticker, interval)
    df = df.copy()
    # parquet preserves index, but keep it explicit for safety
    df.to_parquet(p)


def fetch_yf(ticker: str, interval: str, start: datetime, end: datetime, auto_adjust: bool = True) -> pd.DataFrame:
    df = yf.Ticker(ticker).history(
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        interval=interval,
        auto_adjust=auto_adjust,
    )
    return _normalize(df)


def sync(ticker: str, interval: str = "1h", lookback_days: int = 60, cfg: Optional[StoreConfig] = None) -> pd.DataFrame:
    """Sync recent window from yfinance and merge into local parquet."""
    cfg = cfg or StoreConfig()
    existing = load_local(ticker, interval, cfg)

    end = datetime.now() + timedelta(days=1)  # yfinance end non-inclusive
    start = end - timedelta(days=int(lookback_days))

    fetched = fetch_yf(ticker, interval, start=start, end=end)
    if fetched.empty and not existing.empty:
        return existing

    merged = pd.concat([existing, fetched], axis=0) if not existing.empty else fetched
    merged = merged[~merged.index.duplicated(keep="last")].sort_index()
    save_local(ticker, merged, interval, cfg)
    return merged


def sync_and_load(ticker: str, interval: str = "1h", lookback_days: int = 60, cfg: Optional[StoreConfig] = None) -> pd.DataFrame:
    return sync(ticker, interval=interval, lookback_days=lookback_days, cfg=cfg)
