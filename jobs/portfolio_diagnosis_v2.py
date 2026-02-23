"""
持仓诊断分析引擎 v2 - 分层评估体系

Layer 1: 趋势过滤（硬性门槛）→ 决定"能不能加仓"
Layer 2: 质量评分 → 决定"值得多少仓位"

数据时效性标注：所有基本面数据都标注"截至日期"
"""
import warnings
warnings.filterwarnings('ignore')
import yfinance as yf
import json, os
from datetime import datetime, timedelta

OUTPUT_FILE  = os.path.join(os.path.dirname(__file__), '../dashboard/diagnosis.json')
ROOT_OUTPUT  = os.path.join(os.path.dirname(__file__), '../diagnosis.json')

# 持仓数据
POSITIONS = [
    {'ticker':'TSLA','name':'特斯拉',          'shares':32, 'cost':228.06},
    {'ticker':'META','name':'Meta Platforms',  'shares':15, 'cost':639.088},
    {'ticker':'CRWD','name':'CrowdStrike',     'shares':22, 'cost':463.636},
    {'ticker':'PANW','name':'Palo Alto Net.',  'shares':56, 'cost':183.857},
    {'ticker':'ORCL','name':'甲骨文',           'shares':33, 'cost':186.333},
    {'ticker':'RKLB','name':'Rocket Lab',      'shares':65, 'cost':84.923},
    {'ticker':'OKLO','name':'Oklo Inc',        'shares':65, 'cost':85.108},
    {'ticker':'SOUN','name':'SoundHound AI',   'shares':450,'cost':11.556},
    {'ticker':'SNOW','name':'Snowflake',       'shares':20, 'cost':217.30},
    {'ticker':'ARM', 'name':'Arm Holdings',    'shares':25, 'cost':120.00},
    {'ticker':'AMD', 'name':'美国超微公司',     'shares':15, 'cost':194.533},
    {'ticker':'NNE', 'name':'NANO Nuclear',    'shares':120,'cost':30.00},
    {'ticker':'SOFI','name':'SoFi Technologies','shares':150,'cost':24.693},
    {'ticker':'DXYZ','name':'Destiny Tech100', 'shares':100,'cost':30.10},
    {'ticker':'ASTS','name':'AST SpaceMobile', 'shares':30, 'cost':97.00},
    {'ticker':'NBIS','name':'NEBIUS',          'shares':15, 'cost':31.81},
    {'ticker':'IONQ','name':'IonQ Inc',        'shares':20, 'cost':45.00},
]

# ─────────────────────────────────────────────────────────────
# Layer 1: 趋势过滤（硬性门槛）
# ─────────────────────────────────────────────────────────────

TREND_THRESHOLDS = {
    'healthy':    -5,   # >-5% 趋势健康
    'weak':       -10,  # -5%~-10% 趋势转弱
    'broken':     -20,  # -10%~-20% 趋势破位
    'critical':   -99,  # <-20% 严重破位
}

def assess_trend_filter(tech: dict, spy_hist=None, stock_hist=None) -> dict:
    """
    Layer 1: 趋势过滤
    
    返回：
    - can_add: 是否允许加仓
    - can_hold: 是否值得持有
    - trend_status: 趋势状态
    - reasons: 原因列表
    """
    reasons = []
    can_add = True
    can_hold = True
    
    vs_ma200 = tech.get('vs_ma200')
    vs_ma50 = tech.get('vs_ma50')
    vs_ma20 = tech.get('vs_ma20')
    rsi = tech.get('rsi', 50)
    
    # MA200 偏离度（核心指标）
    if vs_ma200 is not None:
        if vs_ma200 < TREND_THRESHOLDS['critical']:
            can_add = False
            can_hold = False
            reasons.append(f"❌ MA200 下方{abs(vs_ma200):.1f}%，趋势严重破位")
        elif vs_ma200 < TREND_THRESHOLDS['broken']:
            can_add = False
            reasons.append(f"⚠️ MA200 下方{abs(vs_ma200):.1f}%，趋势破位，禁止加仓")
        elif vs_ma200 < TREND_THRESHOLDS['weak']:
            can_add = False
            reasons.append(f"⚠️ MA200 下方{abs(vs_ma200):.1f}%，趋势转弱，暂不加仓")
        else:
            reasons.append(f"✅ MA200 上方{vs_ma200:.1f}%，趋势健康")
    
    # MA50 偏离度（中期趋势）
    if vs_ma50 is not None and vs_ma50 < -15:
        can_add = False
        reasons.append(f"⚠️ MA50 下方{abs(vs_ma50):.1f}%，中期趋势偏弱")
    
    # RSI 极端值
    if rsi > 75:
        can_add = False
        reasons.append(f"⚠️ RSI={rsi:.0f} 超买区，追高风险")
    elif rsi < 20:
        reasons.append(f"✅ RSI={rsi:.0f} 超卖区，可能反弹")
    
    # 相对强度（vs SPY）
    if spy_hist is not None and stock_hist is not None:
        try:
            spy_ret = spy_hist['Close'].pct_change(20).iloc[-1]
            stock_ret = stock_hist['Close'].pct_change(20).iloc[-1]
            rel_strength = (stock_ret - spy_ret) * 100
            
            if rel_strength < -15:
                can_add = False
                reasons.append(f"❌ 20 日跑输大盘{abs(rel_strength):.1f}%，相对强度弱")
            elif rel_strength < -5:
                reasons.append(f"⚠️ 20 日跑输大盘{abs(rel_strength):.1f}%")
            elif rel_strength > 5:
                reasons.append(f"✅ 20 日跑赢大盘{rel_strength:.1f}%")
        except:
            pass
    
    # 成交量确认（量比）
    vol_ratio = tech.get('vol_ratio')
    if vol_ratio is not None:
        if vol_ratio < 0.5:
            reasons.append(f"⚠️ 量比{vol_ratio:.2f}，流动性萎缩")
        elif vol_ratio > 2.0:
            reasons.append(f"✅ 量比{vol_ratio:.2f}，资金活跃")
    
    trend_status = 'critical' if not can_hold else ('broken' if not can_add else ('weak' if any('⚠️' in r for r in reasons) else 'healthy'))
    
    return {
        'can_add': can_add,
        'can_hold': can_hold,
        'trend_status': trend_status,
        'reasons': reasons,
    }


# ─────────────────────────────────────────────────────────────
# Layer 2: 质量评分（决定仓位）
# ─────────────────────────────────────────────────────────────

def calc_quality_score(pos: dict, tech: dict, fund: dict, analyst: dict) -> dict:
    """
    Layer 2: 质量评分
    
    权重分配（总分 100）：
    - 技术面：40 分（实时，短线最重要）
    - 基本面：35 分（季度，但反映质量）
    - 分析师：15 分（参考）
    - 相对强度：10 分（动量）
    """
    score = 0
    details = []
    
    # ── 技术面（40 分）────────────────────────────────
    tech_score = 0
    
    # RSI 位置（10 分）
    rsi = tech.get('rsi', 50)
    if 25 <= rsi <= 45:
        tech_score += 10
        details.append("RSI 低位，反弹潜力")
    elif 45 < rsi <= 55:
        tech_score += 5
        details.append("RSI 中性")
    elif rsi > 70:
        tech_score -= 5
        details.append("RSI 超买，回调风险")
    elif rsi < 25:
        tech_score += 8
        details.append("RSI 超卖，可能反弹")
    
    # MACD 动能（10 分）
    macd_bull = tech.get('macd', 0) > tech.get('macd_sig', 0)
    if macd_bull:
        tech_score += 10
        details.append("MACD 金叉，动能向上")
    else:
        tech_score -= 5
        details.append("MACD 死叉，动能偏弱")
    
    # 价格位置（10 分）
    vs_ma200 = tech.get('vs_ma200')
    if vs_ma200 is not None:
        if vs_ma200 > 5:
            tech_score += 10
        elif vs_ma200 > 0:
            tech_score += 5
        elif vs_ma200 > -10:
            tech_score -= 5
        else:
            tech_score -= 10
    
    # 52 周位置（10 分）
    off_hi = tech.get('off_hi', 0)
    if off_hi > -20:
        tech_score += 10
        details.append("接近 52 周高位，强势")
    elif off_hi > -40:
        tech_score += 5
        details.append("52 周中位")
    else:
        tech_score -= 5
        details.append("远离 52 周高位，弱势")
    
    score += tech_score
    details.append(f"技术面小计：{tech_score}/40")
    
    # ── 基本面（35 分）───────────────────────────────
    fund_score = 0
    
    # 营收增长（15 分）
    rev_growth = fund.get('rev_growth')
    if rev_growth is not None:
        if rev_growth > 0.3:
            fund_score += 15
            details.append(f"营收高增长 +{rev_growth*100:.0f}%")
        elif rev_growth > 0.1:
            fund_score += 10
            details.append(f"营收稳健增长 +{rev_growth*100:.0f}%")
        elif rev_growth > 0:
            fund_score += 5
            details.append(f"营收微增 +{rev_growth*100:.0f}%")
        else:
            fund_score -= 10
            details.append(f"营收下滑 {rev_growth*100:.0f}%")
    
    # 毛利率（10 分）
    gm = fund.get('gross_margin')
    if gm is not None:
        if gm > 0.7:
            fund_score += 10
            details.append(f"毛利率{gm*100:.0f}%，护城河深")
        elif gm > 0.5:
            fund_score += 7
            details.append(f"毛利率{gm*100:.0f}%，良好")
        elif gm > 0.3:
            fund_score += 3
        else:
            fund_score -= 5
    
    # 盈利质量（10 分）- 如有数据
    op_margin = fund.get('op_margin')
    if op_margin is not None:
        if op_margin > 0.2:
            fund_score += 10
            details.append(f"经营利润率{op_margin*100:.0f}%")
        elif op_margin > 0.1:
            fund_score += 5
        elif op_margin < 0:
            fund_score -= 5
            details.append("经营亏损")
    
    score += fund_score
    details.append(f"基本面小计：{fund_score}/35")
    
    # ── 分析师（15 分）───────────────────────────────
    analyst_score = 0
    
    rec = analyst.get('recommendation', '').lower()
    upside = analyst.get('upside', 0) or 0
    
    if rec in ['strong_buy']:
        analyst_score += 10
    elif rec in ['buy']:
        analyst_score += 7
    elif rec in ['hold']:
        analyst_score += 3
    elif rec in ['sell', 'strong_sell']:
        analyst_score -= 5
    
    if upside > 30:
        analyst_score += 5
    elif upside > 15:
        analyst_score += 3
    elif upside < -10:
        analyst_score -= 5
    
    score += analyst_score
    details.append(f"分析师小计：{analyst_score}/15")
    
    # ── 相对强度（10 分）─────────────────────────────
    rel_strength = tech.get('rel_strength', 0)
    if rel_strength is not None:
        if rel_strength > 10:
            score += 10
            details.append(f"相对强度强 +{rel_strength:.1f}%")
        elif rel_strength > 0:
            score += 5
        elif rel_strength < -10:
            score -= 5
            details.append(f"相对强度弱 {rel_strength:.1f}%")
    
    details.append(f"相对强度：{rel_strength if rel_strength else 'N/A'}")
    
    # 最终分数（0-100）
    final_score = max(0, min(100, 50 + score))  # 基准 50 分
    
    return {
        'score': round(final_score, 1),
        'tech_score': tech_score,
        'fund_score': fund_score,
        'analyst_score': analyst_score,
        'details': details,
    }


# ─────────────────────────────────────────────────────────────
# 技术分析
# ─────────────────────────────────────────────────────────────

def calc_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss
    return (100 - 100 / (1 + rs)).iloc[-1]


def calc_macd(close):
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9).mean()
    return macd.iloc[-1], signal.iloc[-1]


def analyze_ticker(pos: dict) -> dict:
    ticker = pos['ticker']
    cost = pos['cost']
    shares = pos['shares']
    print(f"  分析 {ticker}...")

    result = {
        'ticker': ticker,
        'name': pos['name'],
        'cost': cost,
        'shares': shares,
    }

    try:
        tk = yf.Ticker(ticker)
        info = tk.info
        hist = tk.history(period='1y', interval='1d')

        if hist.empty or len(hist) < 30:
            result['error'] = '数据不足'
            return result

        close = hist['Close']
        price = float(close.iloc[-1])
        pnl_pct = (price - cost) / cost * 100
        volume = hist['Volume']

        result['price'] = round(price, 2)
        result['pnl_pct'] = round(pnl_pct, 2)
        result['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')

        # ── 技术指标 ──────────────────────────────────
        ma20 = float(close.rolling(20).mean().iloc[-1])
        ma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
        ma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
        rsi = float(calc_rsi(close))
        macd_val, macd_sig = calc_macd(close)
        
        # 成交量：20 日平均 vs 今日
        vol_20avg = volume.rolling(20).mean().iloc[-1]
        vol_today = volume.iloc[-1]
        vol_ratio = vol_today / vol_20avg if vol_20avg > 0 else 1.0

        # 52 周高低
        hi52 = float(close.rolling(252).max().iloc[-1]) if len(close) >= 252 else float(close.max())
        lo52 = float(close.rolling(252).min().iloc[-1]) if len(close) >= 252 else float(close.min())
        off_hi = (price - hi52) / hi52 * 100

        tech = {
            'price': round(price, 2),
            'ma20': round(ma20, 2),
            'ma50': round(ma50, 2) if ma50 else None,
            'ma200': round(ma200, 2) if ma200 else None,
            'rsi': round(rsi, 1),
            'macd': round(float(macd_val), 3),
            'macd_sig': round(float(macd_sig), 3),
            'hi52': round(hi52, 2),
            'lo52': round(lo52, 2),
            'off_hi': round(off_hi, 1),
            'vs_ma20': round((price/ma20 - 1)*100, 1),
            'vs_ma50': round((price/ma50 - 1)*100, 1) if ma50 else None,
            'vs_ma200': round((price/ma200 - 1)*100, 1) if ma200 else None,
            'vol_ratio': round(vol_ratio, 2),
        }
        result['tech'] = tech

        # ── 基本面（标注时效）───────────────────────────
        fund = {
            'forward_pe': info.get('forwardPE'),
            'trailing_pe': info.get('trailingPE'),
            'pb': info.get('priceToBook'),
            'ps': info.get('priceToSalesTrailing12Months'),
            'rev_growth': info.get('revenueGrowth'),
            'eps_growth': info.get('earningsGrowth'),
            'gross_margin': info.get('grossMargins'),
            'op_margin': info.get('operatingMargins'),
            'roe': info.get('returnOnEquity'),
            'debt_equity': info.get('debtToEquity'),
            'beta': info.get('beta'),
            'market_cap': info.get('marketCap'),
            'sector': info.get('sector', ''),
            'industry': info.get('industry', ''),
            # 时效标注
            'data_note': '基本面数据来自最新财报（可能滞后 1-3 个月）',
        }
        result['fund'] = fund

        # ── 分析师（标注时效）──────────────────────────
        analyst = {
            'recommendation': info.get('recommendationKey', ''),
            'num_analysts': info.get('numberOfAnalystOpinions'),
            'target_mean': info.get('targetMeanPrice'),
            'target_high': info.get('targetHighPrice'),
            'target_low': info.get('targetLowPrice'),
            'data_note': '分析师评级可能滞后数天到数周',
        }
        if analyst['target_mean'] and price:
            analyst['upside'] = round((analyst['target_mean'] - price) / price * 100, 1)
        result['analyst'] = analyst

        # ── Layer 1: 趋势过滤 ─────────────────────────
        trend = assess_trend_filter(tech)
        result['trend'] = trend

        # ── Layer 2: 质量评分 ─────────────────────────
        quality = calc_quality_score(pos, tech, fund, analyst)
        result['quality'] = quality

        # ── 综合建议（结合两层）────────────────────────
        if not trend['can_hold']:
            action = 'exit'
            action_text = '建议止损/离场'
            action_color = 'bearish'
        elif not trend['can_add']:
            if quality['score'] >= 60:
                action = 'hold'
                action_text = '观望持有（趋势弱但质量尚可）'
                action_color = 'neutral'
            else:
                action = 'reduce'
                action_text = '考虑减仓（趋势弱 + 质量一般）'
                action_color = 'caution'
        else:
            # 趋势健康，看质量决定
            if quality['score'] >= 70:
                action = 'hold_or_add'
                action_text = '持有/可加仓'
                action_color = 'bullish'
            elif quality['score'] >= 50:
                action = 'hold'
                action_text = '持有'
                action_color = 'neutral'
            else:
                action = 'reduce'
                action_text = '考虑减仓'
                action_color = 'caution'

        # 诊断信号
        signals = []
        signals.extend([{'type': 'info', 'text': r} for r in trend['reasons']])
        signals.extend([{'type': 'info', 'text': d} for d in quality['details'] if ':' in d])
        
        # 盈亏提醒
        if pnl_pct < -25:
            signals.append({'type': 'warning', 'text': f'⚠️ 已亏损{pnl_pct:.1f}%，评估是否止损'})
        if pnl_pct > 50:
            signals.append({'type': 'caution', 'text': f'✨ 已盈利{pnl_pct:.1f}%，考虑分批止盈'})

        result['diagnosis'] = {
            'score': quality['score'],
            'action': action,
            'action_text': action_text,
            'action_color': action_color,
            'trend_status': trend['trend_status'],
            'can_add': trend['can_add'],
            'can_hold': trend['can_hold'],
            'signals': signals,
        }

    except Exception as e:
        result['error'] = str(e)
        print(f"    ⚠️ {ticker} 分析失败：{e}")

    return result


def _rec_zh(rec):
    return {'strong_buy': '强烈买入', 'buy': '买入', 'hold': '持有',
            'underperform': '低配', 'sell': '卖出', 'strong_sell': '强烈卖出'}.get(rec, rec)


def generate_portfolio_overview(results: list) -> dict:
    """整体持仓健康度分析"""
    valid = [r for r in results if 'diagnosis' in r]
    scores = [r['diagnosis']['score'] for r in valid]
    avg_score = sum(scores) / len(scores) if scores else 50

    # 按行动分类
    actions = {}
    for r in valid:
        a = r['diagnosis']['action']
        actions[a] = actions.get(a, 0) + 1

    # 趋势状态分布
    trend_dist = {}
    for r in valid:
        t = r.get('trend', {}).get('trend_status', 'unknown')
        trend_dist[t] = trend_dist.get(t, 0) + 1

    # 健康度标签
    if avg_score >= 70:
        health_label = '健康'
        health_color = 'bullish'
    elif avg_score >= 50:
        health_label = '中性'
        health_color = 'neutral'
    else:
        health_label = '偏弱'
        health_color = 'bearish'

    return {
        'avg_score': round(avg_score, 1),
        'health_label': health_label,
        'health_color': health_color,
        'total_count': len(valid),
        'actions': actions,
        'trend_distribution': trend_dist,
        'generated_at': datetime.now().isoformat(),
    }


def run():
    print(f"📊 持仓诊断 v2 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  共 {len(POSITIONS)} 只持仓...\n")

    results = []
    for pos in POSITIONS:
        r = analyze_ticker(pos)
        results.append(r)

    overview = generate_portfolio_overview(results)

    output = {
        'generated_at': datetime.now().isoformat(),
        'version': '2.0',
        'overview': overview,
        'stocks': results,
    }

    with open(OUTPUT_FILE, 'w') as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)
    with open(ROOT_OUTPUT, 'w') as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n✅ 诊断完成：{overview['total_count']}只，平均健康度{overview['avg_score']:.1f}（{overview['health_label']}）")
    print(f"   趋势分布：{overview['trend_distribution']}")
    print(f"   行动建议：{overview['actions']}")
    print(f"   已保存：{OUTPUT_FILE}")


if __name__ == '__main__':
    run()
