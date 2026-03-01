"""Symbol mapping for LongPort/Longbridge.

We only trade US stocks for now.
Strategy tickers are like: TSLA, NVDA.
LongPort OpenAPI uses: TSLA.US, NVDA.US.
"""


def to_longport_symbol(ticker: str) -> str:
    t = (ticker or '').strip().upper()
    if not t:
        raise ValueError('empty ticker')
    if '.' in t:
        return t
    return f"{t}.US"
