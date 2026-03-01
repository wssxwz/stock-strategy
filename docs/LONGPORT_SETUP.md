# LongPort / Longbridge OpenAPI Setup (US only, paper mode)

## 1) Install SDK

```bash
cd /Users/vvusu/work/stock-strategy
source venv/bin/activate
pip install longport
```

## 2) Configure environment variables (recommended layout)

Create a dedicated local secrets file (NOT in git):

```bash
mkdir -p ~/.secrets/env
cp ~/.secrets/env/stock-strategy.env.template ~/.secrets/env/stock-strategy.env
nano ~/.secrets/env/stock-strategy.env
chmod 600 ~/.secrets/env/stock-strategy.env
```

Fill values from Longbridge OpenAPI console:

```bash
export LONGPORT_APP_KEY="..."
export LONGPORT_APP_SECRET="..."
export LONGPORT_ACCESS_TOKEN="..."
```

Load it before running:

```bash
source ~/.secrets/env/stock-strategy.env
```

## 3) Test connectivity (no trading)

```bash
cd /Users/vvusu/work/stock-strategy
source venv/bin/activate
python3 jobs/test_longport_connection.py
```

Expected output:
- QUOTE with last/bid/ask
- TRADE_CTX_OK

## 4) Safety defaults

We start with **paper ledger** only. No real order submission is used by default.

Ledger file:
- `data/trades/paper_ledger.jsonl`

## Paper vs Live env switching (recommended)

Create two local env files:

- `~/.secrets/env/stock-strategy.paper.env`
- `~/.secrets/env/stock-strategy.live.env`

Templates are provided:

- `~/.secrets/env/stock-strategy.paper.env.template`
- `~/.secrets/env/stock-strategy.live.env.template`

Load paper (safe default):

```bash
source ~/.secrets/env/stock-strategy.paper.env
```

Load live (read-only queries OK; trading requires explicit confirmation):

```bash
source ~/.secrets/env/stock-strategy.live.env
export LIVE_TRADING=YES_I_KNOW
```

## Live trading switch (HARD GUARDED)

Live trading is disabled by default. To enable *actual* order submission you must set both:

```bash
export TRADING_ENV=live
export LIVE_TRADING=YES_I_KNOW
export LIVE_SUBMIT=1
```

If `LIVE_SUBMIT` is not `1`, the system will only print `LIVE_ORDER_DRYRUN` and will not submit.

## Capital constraints (recommended for small accounts)

Set in your env file:

```bash
export MAX_OPEN_POS=1
export MAX_NEW_BUYS_PER_DAY=1
export PRICE_DRIFT_MAX_PCT=0.015
```

- MAX_OPEN_POS: max simultaneous open positions (live)
- MAX_NEW_BUYS_PER_DAY: daily new buys cap
- PRICE_DRIFT_MAX_PCT: if quote last drifts too far from signal price, skip execution

## Small-capital guards (USD)

```bash
export MAX_PRICE_PCT_EQUITY=0.45   # skip if 1 share > 45% of equity
export TOTAL_RISK_CAP=0.02         # portfolio risk cap (sum of (entry-SL)*qty)
```

## Cooldown (rolling time)

After a stop-out, we apply a rolling cooldown (wall-clock) to avoid re-buying the same symbol too soon.

Env:

```bash
export COOLDOWN_HOURS=24
```

Manual stop-out marking (until we have full auto-sell reconciliation):

```bash
python3 jobs/trade_stopout.py TSLA.US --hours 24 --reason "manual stop"
```

## Live exit (sell) automation (hard-gated)

When EXIT_SIGNAL triggers and you have a live position, the system can submit a SELL limit order (marketable).

Guards:
- TRADING_ENV=live
- LIVE_TRADING=YES_I_KNOW
- LIVE_SUBMIT=1 (otherwise prints LIVE_EXIT_DRYRUN)

Stop-loss exits automatically set cooldown (rolling): COOLDOWN_HOURS (default 24).

## Automated exits (state-based)

Preferred: exits are evaluated from `data/trades/trading_state.json` open_positions (entry/sl/tp), using LongPort quotes.
This avoids relying on manual `monitor/portfolio.json`.

When an SL/TP is hit, we submit a SELL (marketable limit) under the same hard guards.


## Price filters

```bash
export MIN_PRICE_USD=5
export MAX_PRICE_PCT_EQUITY=0.35
```

- MIN_PRICE_USD: skip symbols with last price below this threshold
- MAX_PRICE_PCT_EQUITY: skip symbols if 1 share exceeds this fraction of equity

## MR trend filter

For MR signals, execution requires: `above_ma50 == True` OR `ma50_slope >= 0` (best-effort fields from signal).

## Liquidity filter (Scheme3)

For low-priced names (< MIN_PRICE_USD), we only allow execution when liquidity is sufficient:

```bash
export MIN_DOLLAR_VOL_20D=20000000
```

We use `avg_dollar_vol_20d` computed from daily bars: mean(close*volume, 20d).

## Reconcile (MUST before live submit)

To prevent drift between local state and broker positions:

```bash
python3 jobs/reconcile_trading_state.py
```

This updates `data/trades/trading_state.json` (gitignored).

## Order tracking (pending_orders)

We track submitted (or dry-run) orders in `pending_orders` and reconcile on each scan.
Manual run:

```bash
python3 jobs/reconcile_orders.py
```

## Exit-only high-frequency monitor (recommended)

Run during market hours to reduce gap/flash-crash risk:

```bash
python3 monitor/exit_only.py
```

Suggested cron: every 10 minutes during US market hours (UTC 14-19).


## Stop-loss sell escalation (A: exit first)

If STOP_LOSS is triggered and a SELL is still pending, we cancel/replace with more aggressive marketable limits.

```bash
export EXIT_ESCALATE_MAX_ATTEMPTS=3
```

The exit-only monitor prints:
- LIVE_EXIT_ESCALATE_DRYRUN / LIVE_EXIT_ESCALATE_SUBMIT

## Manual intervention alert

When STOP_LOSS escalation reaches max attempts or fails, the system sends a strong Telegram alert via openclaw CLI.

Env:

```bash
export ALERT_CHAT_ID=1041640995
```

## Duplicate order guards

- If a BUY is pending for the same symbol, we skip new BUY intents (SKIP_PENDING_BUY).
- If a SELL is pending for the same symbol, we skip new SELL intents (exit-only), except STOP_LOSS escalation which cancels/replaces.

## Cash buffer

To avoid using up all cash (fees/settlement), we skip new buys if remaining cash would be below:

```bash
export MIN_CASH_BUFFER_USD=50
```

## Price freshness & execution guards

```bash
export QUOTE_STALE_SEC=60
export DOUBLE_QUOTE_DRIFT_PCT=0.006
export MAX_SPREAD_PCT=0.008
```

- QUOTE_STALE_SEC: skip if quote is too old
- DOUBLE_QUOTE_DRIFT_PCT: skip if two consecutive quotes drift too much
- MAX_SPREAD_PCT: skip if bid/ask spread too wide (when available)
