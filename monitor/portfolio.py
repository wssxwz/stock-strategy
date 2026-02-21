"""
持仓管理模块
记录开仓信息，监控止盈止损条件，触发卖出提醒
"""
import json, os
from datetime import datetime

PORTFOLIO_FILE = os.path.join(os.path.dirname(__file__), 'portfolio.json')


def load_portfolio() -> dict:
    if os.path.exists(PORTFOLIO_FILE):
        with open(PORTFOLIO_FILE) as f:
            return json.load(f)
    return {}


def save_portfolio(portfolio: dict):
    with open(PORTFOLIO_FILE, 'w') as f:
        json.dump(portfolio, f, indent=2, default=str)


def add_position(ticker: str, entry_price: float, tp: float, sl: float, note: str = ''):
    """手动记录开仓（收到买入信号后，你决定买了可以登记）"""
    portfolio = load_portfolio()
    portfolio[ticker] = {
        'ticker':      ticker,
        'entry_price': entry_price,
        'take_profit': tp,
        'stop_loss':   sl,
        'entry_time':  datetime.now().isoformat(),
        'note':        note,
        'alerted':     [],   # 已发送过的预警类型，避免重复
    }
    save_portfolio(portfolio)
    print(f"✅ 已记录持仓: {ticker} @{entry_price}  止盈:{tp}  止损:{sl}")


def check_positions(current_prices: dict) -> list:
    """
    检查所有持仓的止盈止损状态
    current_prices: {ticker: price}
    返回需要发送的提醒列表
    """
    portfolio = load_portfolio()
    alerts = []

    for ticker, pos in portfolio.items():
        price = current_prices.get(ticker)
        if not price:
            continue

        entry  = pos['entry_price']
        tp     = pos['take_profit']
        sl     = pos['stop_loss']
        ret    = (price - entry) / entry * 100
        alerted = pos.get('alerted', [])

        alert = None

        # ── 止盈触发 ──
        if price >= tp and '止盈' not in alerted:
            alert = {
                'type':   '止盈',
                'ticker': ticker,
                'price':  price,
                'entry':  entry,
                'ret':    round(ret, 2),
                'tp':     tp,
                'sl':     sl,
                'emoji':  '🎯',
                'msg':    f'已达止盈目标 +{ret:.1f}%，建议出场'
            }
            pos['alerted'].append('止盈')

        # ── 止损触发 ──
        elif price <= sl and '止损' not in alerted:
            alert = {
                'type':   '止损',
                'ticker': ticker,
                'price':  price,
                'entry':  entry,
                'ret':    round(ret, 2),
                'tp':     tp,
                'sl':     sl,
                'emoji':  '🛡️',
                'msg':    f'已触及止损位 {ret:.1f}%，建议止损出场'
            }
            pos['alerted'].append('止损')

        # ── 接近止损预警（距止损还有2%）──
        elif (price - sl) / entry * 100 < 2 and '止损预警' not in alerted:
            alert = {
                'type':   '止损预警',
                'ticker': ticker,
                'price':  price,
                'entry':  entry,
                'ret':    round(ret, 2),
                'tp':     tp,
                'sl':     sl,
                'emoji':  '⚠️',
                'msg':    f'接近止损位！当前{ret:.1f}%，止损位{sl}，请注意'
            }
            pos['alerted'].append('止损预警')

        # ── 浮盈回撤预警（盈利超过5%后回撤超过3%）──
        elif ret < -3 and max(0, (price/entry-1)*100) > 5 and '回撤预警' not in alerted:
            alert = {
                'type':   '回撤预警',
                'ticker': ticker,
                'price':  price,
                'entry':  entry,
                'ret':    round(ret, 2),
                'tp':     tp,
                'sl':     sl,
                'emoji':  '📉',
                'msg':    f'浮盈回撤，当前{ret:.1f}%，考虑移动止损'
            }
            pos['alerted'].append('回撤预警')

        if alert:
            alerts.append(alert)

    save_portfolio(portfolio)
    return alerts


def format_exit_alert(alert: dict) -> str:
    """格式化卖出提醒消息"""
    ret_str = f"+{alert['ret']}%" if alert['ret'] > 0 else f"{alert['ret']}%"
    color = "🟢" if alert['ret'] > 0 else "🔴"

    return f"""{alert['emoji']} **{alert['ticker']}** — {alert['type']}提醒
━━━━━━━━━━━━━━━━━━
{color} 当前价: ${alert['price']}
📊 浮动盈亏: {ret_str}
📌 开仓价: ${alert['entry']}
🎯 止盈位: ${alert['tp']}  🛡️ 止损位: ${alert['sl']}

💬 {alert['msg']}

_仅供参考，最终决策由您判断_"""


def list_positions():
    """打印当前所有持仓"""
    portfolio = load_portfolio()
    if not portfolio:
        print("📭 当前无持仓记录")
        return
    print(f"\n{'='*55}")
    print(f"📋 当前持仓 ({len(portfolio)} 只)")
    print(f"{'='*55}")
    print(f"{'股票':<7} {'开仓价':>8} {'止盈':>8} {'止损':>8} {'开仓时间'}")
    print(f"{'─'*55}")
    for t, p in portfolio.items():
        print(f"{t:<7} {p['entry_price']:>8.2f} {p['take_profit']:>8.2f} {p['stop_loss']:>8.2f}  {p['entry_time'][:16]}")
