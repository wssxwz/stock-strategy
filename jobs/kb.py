"""
知识库加载模块 - 所有 job 通过此模块读取用户偏好
"""
import json, os

_KB_PATH = os.path.join(os.path.dirname(__file__), '../data/knowledge_base.json')

def load() -> dict:
    with open(_KB_PATH) as f:
        return json.load(f)

def get_core_holdings() -> list:
    """返回核心重仓股 ticker 列表"""
    kb = load()
    return [s['ticker'] for s in kb['core_holdings']['stocks']]

def get_focus_tickers() -> list:
    """返回所有重点关注股票"""
    kb = load()
    t1 = kb['watchlist_priority']['tier1_core']
    t2 = kb['watchlist_priority']['tier2_focus']
    return list(dict.fromkeys(t1 + t2))  # 去重保序

def get_focus_sectors() -> list:
    """返回关注板块名称列表"""
    kb = load()
    return [s['name'] for s in kb['focus_sectors']['priority']]

def get_sector_etfs() -> dict:
    """返回板块→ETF映射"""
    kb = load()
    # 只取主ETF（第一个）
    return {k: v[0] for k, v in kb['sector_etf_map'].items()}

def get_risk_profile() -> dict:
    return load()['risk_profile']

def is_in_focus(ticker: str) -> bool:
    """判断某股是否在重点关注池"""
    focus = get_focus_tickers()
    kb = load()
    all_kw = []
    for s in kb['focus_sectors']['priority']:
        all_kw += s.get('keywords', [])
    return ticker in focus or ticker in all_kw

def score_bonus(ticker: str) -> int:
    """
    核心持仓加权分数
    tier1 核心持仓: +15分
    tier2 重点关注: +8分
    其他: 0分
    """
    kb = load()
    if ticker in kb['watchlist_priority']['tier1_core']:
        return 15
    if ticker in kb['watchlist_priority']['tier2_focus']:
        return 8
    return 0
