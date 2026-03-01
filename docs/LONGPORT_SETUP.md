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
