# LongPort / Longbridge OpenAPI Setup (US only, paper mode)

## 1) Install SDK

```bash
cd /Users/vvusu/work/stock-strategy
source venv/bin/activate
pip install longport
```

## 2) Configure environment variables

Get values from Longbridge OpenAPI console.

```bash
export LONGPORT_APP_KEY="..."
export LONGPORT_APP_SECRET="..."
export LONGPORT_ACCESS_TOKEN="..."
```

Recommended: put them in `~/.zshrc` or a dedicated `~/.longport.env` file.

Example `~/.longport.env`:

```bash
export LONGPORT_APP_KEY="..."
export LONGPORT_APP_SECRET="..."
export LONGPORT_ACCESS_TOKEN="..."
```

Load it:

```bash
source ~/.longport.env
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
