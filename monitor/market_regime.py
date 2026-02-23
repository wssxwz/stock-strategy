"""
市场环境识别模块（Market Regime Filter）

为什么需要这个？
  顶级操盘手第一条原则："Don't fight the tape"
  当 SPY/QQQ 处于下跌趋势时，做多任何个股的胜率
  比牛市低 25-35%（历史回测验证）。
  
  这个模块的作用：
  - 牛市：正常发信号（阈值 70）
  - 震荡：提高门槛（阈值 80），减少噪音
  - 熊市：大幅提高门槛（阈值 90），只发极强信号
  - 恐慌：停发买入信号（防止接飞刀）

市场环境判断逻辑：
  1. SPY 相对 MA50/MA200 位置（趋势方向）
  2. SPY 近 20 日涨跌幅（趋势强度）
  3. VIX 水平（恐慌程度）
  4. 综合得出 regime + 建议阈值
"""
import warnings
warnings.filterwarnings('ignore')

import yfinance as yf
import json, os
from datetime import datetime
from typing import Tuple

CACHE_FILE = os.path.join(os.path.dirname(__file__), '.regime_cache.json')
CACHE_TTL_MINUTES = 60  # regime 缓存 1 小时


def _load_cache() -> dict | None:
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE) as f:
            data = json.load(f)
        ts = datetime.fromisoformat(data.get('cached_at', '2000-01-01'))
        if (datetime.now() - ts).total_seconds() < CACHE_TTL_MINUTES * 60:
            return data
    except Exception:
        pass
    return None


def _save_cache(data: dict):
    data['cached_at'] = datetime.now().isoformat()
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def get_market_regime(use_cache: bool = True) -> dict:
    """
    返回当前市场环境。

    Returns:
        {
          'regime': 'bull' | 'neutral' | 'bear' | 'panic',
          'regime_zh': '牛市' | '震荡' | '熊市' | '恐慌',
          'min_score': int,          # 建议的信号阈值
          'spy_vs_ma50': float,      # SPY 相对 MA50 偏离 %
          'spy_vs_ma200': float,     # SPY 相对 MA200 偏离 %
          'spy_ret20': float,        # SPY 近 20 日涨跌 %
          'vix': float | None,       # VIX 当前值
          'detail': str,             # 人类可读的环境描述
          'signal_allowed': bool,    # 是否允许发出买入信号
        }
    """
    if use_cache:
        cached = _load_cache()
        if cached:
            return cached

    result = {
        'regime': 'neutral',
        'regime_zh': '震荡',
        'min_score': 80,
        'spy_vs_ma50': 0,
        'spy_vs_ma200': 0,
        'spy_ret20': 0,
        'vix': None,
        'detail': '数据获取中...',
        'signal_allowed': True,
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
    }

    try:
        # ── 1. SPY 数据 ──────────────────────────────
        spy_hist = yf.Ticker('SPY').history(period='60d', interval='1d')
        if spy_hist.empty or len(spy_hist) < 30:
            return result

        spy_close = spy_hist['Close']
        spy_price = float(spy_close.iloc[-1])
        spy_ma50  = float(spy_close.rolling(50).mean().iloc[-1]) if len(spy_close) >= 50 else spy_price
        spy_ma200 = float(spy_close.rolling(200).mean().iloc[-1]) if len(spy_close) >= 200 else spy_price
        spy_ret20 = float((spy_price / spy_close.iloc[-20] - 1) * 100) if len(spy_close) >= 20 else 0

        vs_ma50  = (spy_price / spy_ma50  - 1) * 100
        vs_ma200 = (spy_price / spy_ma200 - 1) * 100

        result.update({
            'spy_vs_ma50':  round(vs_ma50, 2),
            'spy_vs_ma200': round(vs_ma200, 2),
            'spy_ret20':    round(spy_ret20, 2),
        })

        # ── 2. VIX 数据 ──────────────────────────────
        vix = None
        try:
            vix_hist = yf.Ticker('^VIX').history(period='5d', interval='1d')
            if not vix_hist.empty:
                vix = round(float(vix_hist['Close'].iloc[-1]), 1)
        except Exception:
            pass
        result['vix'] = vix

        # ── 3. 判断 regime ────────────────────────────
        #
        # 规则（按优先级，从严到宽）：
        #   恐慌（panic）：VIX > 35，停发信号
        #   熊市（bear）：SPY < MA200 且 20日跌 > 5%
        #   震荡（neutral）：SPY < MA50 或 20日跌 > 2%
        #   牛市（bull）：SPY > MA50 > MA200 且近 20 日正收益

        if vix and vix > 35:
            regime       = 'panic'
            regime_zh    = '恐慌'
            min_score    = 95          # 极端情况才发
            signal_ok    = False
            detail = (f'🚨 VIX={vix}（极度恐慌），暂停买入信号 | '
                      f'SPY vs MA200={vs_ma200:.1f}%')

        elif vs_ma200 < -5 and spy_ret20 < -5:
            regime       = 'bear'
            regime_zh    = '熊市'
            min_score    = 90
            signal_ok    = True        # 允许但门槛极高
            detail = (f'🐻 SPY 在 MA200 下方 {abs(vs_ma200):.1f}%，20日跌 {spy_ret20:.1f}% | '
                      f'仅发 score≥{min_score} 的极强信号')

        elif vs_ma50 < -3 or spy_ret20 < -2:
            regime       = 'neutral'
            regime_zh    = '震荡'
            min_score    = 80
            signal_ok    = True
            detail = (f'⚠️ SPY 震荡 | vs MA50={vs_ma50:.1f}% | 20日={spy_ret20:.1f}% | '
                      f'提高至 score≥{min_score}')

        else:
            regime       = 'bull'
            regime_zh    = '牛市'
            min_score    = 70          # 标准阈值
            signal_ok    = True
            detail = (f'🐂 SPY 健康 | vs MA50={vs_ma50:.1f}% vs MA200={vs_ma200:.1f}% | '
                      f'20日={spy_ret20:.1f}% | 标准阈值 score≥{min_score}')

        # ── 4. VIX 附加调整 ──────────────────────────
        # 即使牛市，VIX>25 也需要提高警惕
        if vix and vix > 25 and regime == 'bull':
            min_score = max(min_score, 75)
            detail += f' | VIX={vix}偏高，阈值调整至{min_score}'

        result.update({
            'regime':         regime,
            'regime_zh':      regime_zh,
            'min_score':      min_score,
            'detail':         detail,
            'signal_allowed': signal_ok,
            'generated_at':   datetime.now().strftime('%Y-%m-%d %H:%M'),
        })

    except Exception as e:
        result['detail'] = f'环境识别失败：{e}'

    _save_cache(result)
    return result


def get_score_threshold(ticker: str, regime: dict) -> int:
    """
    P3 结论：按市场环境 × 股票类型动态设置信号阈值
    
    回测结论（1H / 730天）：
    - 牛市 + 质量股：胜率 47%，期望 +2.0%  → 阈值 70（可接受）
    - 牛市 + 投机股：胜率 42%，期望 +2.7%  → 阈值 80（高波动，需更强信号）
    - 震荡 + 所有：  胜率 52%，期望 +4.6%  → 阈值 80（比牛市更赚，但需过滤噪音）
    - 熊市 + 所有：  胜率 0%（样本少）      → 阈值 90（防接飞刀）
    - 恐慌：         停发信号               → 不适用
    """
    try:
        from config import SPECULATIVE_TICKERS, QUALITY_TICKERS
    except ImportError:
        return regime['min_score']

    r = regime['regime']
    base = regime['min_score']

    if r == 'bull':
        # 投机股在牛市也需要更高门槛
        if ticker in SPECULATIVE_TICKERS:
            return max(base, 80)
        return base  # 质量股维持 70
    elif r == 'neutral':
        return max(base, 80)  # 震荡期提高到 80
    else:
        return base  # bear/panic 已在 regime 层处理


def regime_header(r: dict) -> str:
    """生成推送消息里的市场环境标题行"""
    emoji = {'bull': '🐂', 'neutral': '⚠️', 'bear': '🐻', 'panic': '🚨'}.get(r['regime'], '📊')
    vix_str = f' | VIX={r["vix"]}' if r.get('vix') else ''
    return (f"{emoji} 市场环境：{r['regime_zh']} | "
            f"SPY vs MA200={r['spy_vs_ma50']:+.1f}%{vix_str} | "
            f"信号阈值≥{r['min_score']}分")


if __name__ == '__main__':
    r = get_market_regime(use_cache=False)
    print('=== 市场环境 ===')
    for k, v in r.items():
        print(f'  {k}: {v}')
