"""
市场数据采集基础模块
所有 job 共用的数据获取函数
"""
import warnings
warnings.filterwarnings('ignore')

import yfinance as yf
import json, os
from datetime import datetime, timedelta



# ── Ticker aliases (compat): allow ETF-like symbols in upper layers ──
# Many jobs historically use SPY/QQQ/DIA/IWM/VIX while we fetch index bodies.
INDEX_ALIASES = {
    'SPY': '^GSPC',
    'QQQ': '^NDX',
    'DIA': '^DJI',
    'IWM': '^RUT',
    'VIX': '^VIX',
}


def normalize_tickers(tickers):
    # Return (fetch_tickers, alias_map_original_to_fetch)
    alias_map = {}
    fetch = []
    for t in tickers or []:
        t2 = INDEX_ALIASES.get(t, t)
        alias_map[t] = t2
        if t2 not in fetch:
            fetch.append(t2)
    return fetch, alias_map
# ── 核心指数（指数本体）──
# 使用指数代码而非 ETF，避免价格口径混淆
INDICES = {
    '^GSPC':  '标普500',
    '^NDX':   '纳斯达克100',
    '^DJI':   '道琼斯',
    '^RUT':   '罗素2000',
    '^VIX':   'VIX恐慌指数',
}

# ── 大宗商品 ──
COMMODITIES = {
    'GC=F':   '黄金',
    'CL=F':   '原油(WTI)',
    'SI=F':   '白银',
    'NG=F':   '天然气',
}

# ── 外汇 ──
FOREX = {
    'USDJPY=X': '美元/日元',
    'EURUSD=X': '欧元/美元',
    'USDCNH=X': '美元/人民币',
}

# ── 板块 ETF ──
SECTORS = {
    'XLK': '科技',
    'XLF': '金融',
    'XLE': '能源',
    'XLV': '医疗',
    'XLI': '工业',
    'XLC': '通信',
    'XLY': '非必需消费',
    'XLP': '必需消费',
    'XLB': '材料',
    'XLRE': '房地产',
    'XLU': '公用事业',
}


def get_quote(ticker: str) -> dict:
    """获取单只股票最新行情"""
    ticker_fetch = INDEX_ALIASES.get(ticker, ticker)
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period='5d', interval='1d')
        if hist.empty or len(hist) < 2:
            return {}
        
        latest = hist.iloc[-1]
        prev   = hist.iloc[-2]
        price  = float(latest['Close'])
        prev_p = float(prev['Close'])
        chg    = price - prev_p
        chg_pct = chg / prev_p * 100
        
        return {
            'ticker':   ticker,
            'price':    round(price, 2),
            'change':   round(chg, 2),
            'change_pct': round(chg_pct, 2),
            'volume':   int(latest['Volume']) if 'Volume' in latest else 0,
        }
    except Exception as e:
        return {'ticker': ticker, 'error': str(e)}


def get_batch_quotes(tickers: list) -> dict:
    """批量获取行情

    Supports aliases: SPY/QQQ/DIA/IWM/VIX will be mapped to index bodies.
    Returns a dict keyed by the *original* tickers passed in.
    """
    try:
        fetch_tickers, alias_map = normalize_tickers(list(tickers or []))
        raw = yf.download(fetch_tickers, period='5d', interval='1d',
                          auto_adjust=True, progress=False, threads=True)
        results = {}
        for ticker in (tickers or []):
            try:
                fetch = alias_map.get(ticker, ticker)
                if len(fetch_tickers) == 1:
                    closes = raw['Close']
                else:
                    closes = raw['Close'][fetch]
                closes = closes.dropna()
                if len(closes) < 2:
                    continue
                price    = float(closes.iloc[-1])
                prev_p   = float(closes.iloc[-2])
                chg_pct  = (price - prev_p) / prev_p * 100
                results[ticker] = {
                    'price':      round(price, 2),
                    'change_pct': round(chg_pct, 2),
                    'change':     round(price - prev_p, 2),
                }
            except Exception:
                continue
        return results
    except Exception as e:
        print(f"  批量行情失败: {e}")
        return {}


def get_fear_greed() -> dict:
    """
    CNN 恐惧贪婪指数（通过 alternative.me 免费API）
    返回: {'value': 45, 'label': 'Fear', 'label_zh': '恐惧'}
    """
    try:
        import urllib.request
        url = 'https://api.alternative.me/fng/?limit=1'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        item = data['data'][0]
        value = int(item['value'])
        label = item['value_classification']
        labels_zh = {
            'Extreme Fear': '极度恐惧',
            'Fear': '恐惧',
            'Neutral': '中性',
            'Greed': '贪婪',
            'Extreme Greed': '极度贪婪',
        }
        return {
            'value':    value,
            'label':    label,
            'label_zh': labels_zh.get(label, label),
            'emoji':    '😱' if value < 25 else ('😰' if value < 45 else ('😐' if value < 55 else ('😏' if value < 75 else '🤑'))),
        }
    except Exception as e:
        return {'value': 50, 'label': 'Neutral', 'label_zh': '中性（获取失败）', 'emoji': '😐'}


def get_upcoming_earnings(days_ahead: int = 3) -> list:
    """
    获取未来N天的重要财报（从S&P500中筛选市值前50的）
    """
    big_caps = ['AAPL','MSFT','NVDA','AMZN','GOOGL','META','TSLA','BRK-B',
                'AVGO','LLY','JPM','V','UNH','XOM','MA','HD','PG','COST',
                'JNJ','ABBV','BAC','NFLX','CRM','MRK','CVX','ORCL','AMD']
    earnings = []
    today = datetime.now()
    
    for ticker in big_caps[:20]:  # 只取前20，避免太慢
        try:
            t = yf.Ticker(ticker)
            cal = t.calendar
            if cal is None or cal.empty:
                continue
            
            # 财报日期
            if 'Earnings Date' in cal.index:
                earn_dates = cal.loc['Earnings Date']
                for d in (earn_dates if hasattr(earn_dates, '__iter__') else [earn_dates]):
                    try:
                        ed = pd.Timestamp(d).to_pydatetime() if hasattr(d, 'to_pydatetime') else datetime.strptime(str(d)[:10], '%Y-%m-%d')
                        delta = (ed.date() - today.date()).days
                        if 0 <= delta <= days_ahead:
                            earnings.append({
                                'ticker': ticker,
                                'date': ed.strftime('%m-%d'),
                                'days': delta,
                            })
                    except:
                        pass
        except:
            continue
    
    return sorted(earnings, key=lambda x: x['days'])


def get_sector_performance() -> dict:
    """获取11个板块ETF的1日涨跌幅"""
    quotes = get_batch_quotes(list(SECTORS.keys()))
    result = {}
    for etf, name in SECTORS.items():
        if etf in quotes:
            result[etf] = {
                'name': name,
                'change_pct': quotes[etf]['change_pct'],
                'price': quotes[etf]['price'],
            }
    return dict(sorted(result.items(), key=lambda x: x[1]['change_pct'], reverse=True))


def save_daily_data(data: dict, date_str: str = None):
    """保存每日数据到JSON"""
    if not date_str:
        date_str = datetime.now().strftime('%Y-%m-%d')
    
    path = os.path.join(os.path.dirname(__file__), f'../data/daily/{date_str}.json')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    
    existing = {}
    if os.path.exists(path):
        with open(path) as f:
            existing = json.load(f)
    
    existing.update(data)
    existing['updated_at'] = datetime.now().isoformat()
    
    with open(path, 'w') as f:
        json.dump(existing, f, indent=2, default=str)
    
    return path


def load_daily_data(date_str: str = None) -> dict:
    """加载某天的数据"""
    if not date_str:
        date_str = datetime.now().strftime('%Y-%m-%d')
    path = os.path.join(os.path.dirname(__file__), f'../data/daily/{date_str}.json')
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


import pandas as pd  # pandas 放最后避免循环
