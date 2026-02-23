"""
持仓诊断分析引擎
分析每只持仓股票的：技术面、基本面、分析师目标价、持仓合理性
生成 diagnosis.json 供 Dashboard 读取
"""
import warnings
warnings.filterwarnings('ignore')
import yfinance as yf
import json, os
from datetime import datetime

OUTPUT_FILE  = os.path.join(os.path.dirname(__file__), '../dashboard/diagnosis.json')
ROOT_OUTPUT  = os.path.join(os.path.dirname(__file__), '../diagnosis.json')

# 持仓数据（与 app.js 保持一致）
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


def calc_rsi(close, period=14):
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss
    return (100 - 100 / (1 + rs)).iloc[-1]


def calc_macd(close):
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    macd  = ema12 - ema26
    signal= macd.ewm(span=9).mean()
    return macd.iloc[-1], signal.iloc[-1]


def analyze_ticker(pos: dict) -> dict:
    ticker = pos['ticker']
    cost   = pos['cost']
    shares = pos['shares']
    print(f"  分析 {ticker}...")

    result = {
        'ticker': ticker,
        'name':   pos['name'],
        'cost':   cost,
        'shares': shares,
    }

    try:
        tk   = yf.Ticker(ticker)
        info = tk.info
        hist = tk.history(period='1y', interval='1d')

        if hist.empty or len(hist) < 30:
            result['error'] = '数据不足'
            return result

        close = hist['Close']
        price = float(close.iloc[-1])
        pnl_pct = (price - cost) / cost * 100

        result['price']   = round(price, 2)
        result['pnl_pct'] = round(pnl_pct, 2)

        # ── 技术分析 ──────────────────────────────────
        ma20  = float(close.rolling(20).mean().iloc[-1])
        ma50  = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50  else None
        ma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
        rsi   = float(calc_rsi(close))
        macd_val, macd_sig = calc_macd(close)

        hi52 = float(close.rolling(252).max().iloc[-1]) if len(close) >= 50 else price
        lo52 = float(close.rolling(252).min().iloc[-1]) if len(close) >= 50 else price
        off_hi = (price - hi52) / hi52 * 100

        tech = {
            'price':   round(price, 2),
            'ma20':    round(ma20, 2),
            'ma50':    round(ma50, 2)  if ma50  else None,
            'ma200':   round(ma200, 2) if ma200 else None,
            'rsi':     round(rsi, 1),
            'macd':    round(float(macd_val), 3),
            'macd_sig':round(float(macd_sig), 3),
            'hi52':    round(hi52, 2),
            'lo52':    round(lo52, 2),
            'off_hi':  round(off_hi, 1),
            'vs_ma20': round((price/ma20 - 1)*100, 1),
            'vs_ma50': round((price/ma50 - 1)*100, 1) if ma50  else None,
            'vs_ma200':round((price/ma200- 1)*100, 1) if ma200 else None,
        }

        # 技术信号判断
        tech_signals = []
        if rsi < 30:   tech_signals.append({'type':'bullish','text':'RSI超卖(<30)，可能反弹'})
        elif rsi > 70: tech_signals.append({'type':'bearish','text':'RSI超买(>70)，注意回调'})
        elif rsi < 45: tech_signals.append({'type':'neutral','text':f'RSI={rsi:.0f}，处于低位区间'})

        if ma200 and price > ma200: tech_signals.append({'type':'bullish','text':'价格在MA200上方，长期趋势向上'})
        elif ma200: tech_signals.append({'type':'bearish','text':'价格在MA200下方，长期趋势偏空'})

        if ma50 and price < ma50 * 0.9: tech_signals.append({'type':'bearish','text':f'价格大幅低于MA50（-{abs(tech["vs_ma50"]):.1f}%），趋势偏弱'})
        if float(macd_val) > float(macd_sig): tech_signals.append({'type':'bullish','text':'MACD金叉，短期动能向上'})
        else: tech_signals.append({'type':'bearish','text':'MACD死叉，短期动能偏弱'})

        tech['signals'] = tech_signals
        result['tech'] = tech

        # ── 基本面 ────────────────────────────────────
        fund = {
            'forward_pe':     info.get('forwardPE'),
            'trailing_pe':    info.get('trailingPE'),
            'pb':             info.get('priceToBook'),
            'ps':             info.get('priceToSalesTrailing12Months'),
            'rev_growth':     info.get('revenueGrowth'),
            'eps_growth':     info.get('earningsGrowth'),
            'gross_margin':   info.get('grossMargins'),
            'op_margin':      info.get('operatingMargins'),
            'roe':            info.get('returnOnEquity'),
            'debt_equity':    info.get('debtToEquity'),
            'beta':           info.get('beta'),
            'market_cap':     info.get('marketCap'),
            'sector':         info.get('sector',''),
            'industry':       info.get('industry',''),
        }
        fund_signals = []
        if fund['rev_growth'] and fund['rev_growth'] > 0.2:
            fund_signals.append({'type':'bullish','text':f'营收同比增长{fund["rev_growth"]*100:.0f}%，成长性强'})
        elif fund['rev_growth'] and fund['rev_growth'] < 0:
            fund_signals.append({'type':'bearish','text':f'营收同比下滑{fund["rev_growth"]*100:.0f}%，增长承压'})

        if fund['gross_margin'] and fund['gross_margin'] > 0.6:
            fund_signals.append({'type':'bullish','text':f'毛利率{fund["gross_margin"]*100:.0f}%，护城河深厚'})

        if fund['beta'] and fund['beta'] > 1.5:
            fund_signals.append({'type':'neutral','text':f'Beta={fund["beta"]:.2f}，高波动性，适合短线但风险大'})

        fund['signals'] = fund_signals
        result['fund'] = fund

        # ── 分析师目标价 ──────────────────────────────
        analyst = {
            'recommendation': info.get('recommendationKey',''),
            'num_analysts':   info.get('numberOfAnalystOpinions'),
            'target_mean':    info.get('targetMeanPrice'),
            'target_high':    info.get('targetHighPrice'),
            'target_low':     info.get('targetLowPrice'),
        }
        if analyst['target_mean'] and price:
            analyst['upside'] = round((analyst['target_mean'] - price) / price * 100, 1)
        result['analyst'] = analyst

        # ── 持仓诊断 ──────────────────────────────────
        diagnosis = diagnose_position(pos, tech, fund, analyst, pnl_pct)
        result['diagnosis'] = diagnosis

    except Exception as e:
        result['error'] = str(e)
        print(f"    ⚠️ {ticker} 分析失败: {e}")

    return result


def diagnose_position(pos, tech, fund, analyst, pnl_pct):
    """生成持仓综合诊断"""
    ticker = pos['ticker']
    cost   = pos['cost']
    signals= []
    action = 'hold'  # hold / add / reduce / exit
    score  = 50      # 0-100，越高越值得持有

    # 技术面评分
    rsi = tech.get('rsi', 50)
    vs_ma200 = tech.get('vs_ma200')
    macd_bull = tech.get('macd', 0) > tech.get('macd_sig', 0)

    if vs_ma200 and vs_ma200 > 0: score += 10
    else: score -= 10

    if rsi < 35:  score += 10
    elif rsi > 65: score -= 10

    if macd_bull: score += 5
    else: score -= 5

    # 基本面评分
    rev_growth = fund.get('rev_growth') or 0
    gm = fund.get('gross_margin') or 0
    if rev_growth > 0.3: score += 15
    elif rev_growth > 0.1: score += 8
    elif rev_growth < 0: score -= 15

    if gm > 0.6: score += 8
    elif gm < 0.2: score -= 5

    # 分析师评分
    rec = analyst.get('recommendation','').lower()
    upside = analyst.get('upside', 0) or 0
    if rec in ['strong_buy','buy']: score += 10
    elif rec in ['sell','strong_sell']: score -= 15
    if upside > 20: score += 10
    elif upside < -10: score -= 10

    # 持仓盈亏处理
    if pnl_pct < -25:
        signals.append({'type':'warning','text':f'⚠️ 已亏损{pnl_pct:.1f}%，需评估是否触发止损（建议 -8% 止损线）'})
        score -= 15
    if pnl_pct > 50:
        signals.append({'type':'caution','text':f'✨ 已盈利{pnl_pct:.1f}%，可考虑分批止盈，锁定部分利润'})

    # 得出行动建议
    score = max(0, min(100, score))
    if score >= 70:
        action = 'hold_or_add'
        action_text = '持有/可加仓'
        action_color = 'bullish'
    elif score >= 50:
        action = 'hold'
        action_text = '观望持有'
        action_color = 'neutral'
    elif score >= 35:
        action = 'reduce'
        action_text = '考虑减仓'
        action_color = 'caution'
    else:
        action = 'exit'
        action_text = '建议止损/离场'
        action_color = 'bearish'

    # 技术面小结
    ma200_txt = ''
    if vs_ma200 is not None:
        if vs_ma200 > 0:
            ma200_txt = f'价格高于MA200 +{vs_ma200:.1f}%，长线趋势健康'
        else:
            ma200_txt = f'价格低于MA200 {vs_ma200:.1f}%，长线趋势偏空'

    summary = {
        'score':        score,
        'action':       action,
        'action_text':  action_text,
        'action_color': action_color,
        'tech_summary': ma200_txt,
        'rsi_summary':  f'RSI={rsi:.0f}（{"超卖" if rsi<30 else "低位" if rsi<45 else "中性" if rsi<55 else "高位" if rsi<70 else "超买"}）',
        'analyst_summary': f'分析师：{_rec_zh(rec)}，{analyst.get("num_analysts",0)}人覆盖，均价目标${analyst.get("target_mean","--")}（空间{upside:+.1f}%）' if analyst.get('target_mean') else '',
        'signals': signals,
    }
    return summary


def _rec_zh(rec):
    return {'strong_buy':'强烈买入','buy':'买入','hold':'持有',
            'underperform':'低配','sell':'卖出','strong_sell':'强烈卖出'}.get(rec, rec)


def generate_portfolio_overview(results: list) -> dict:
    """整体持仓健康度分析"""
    valid  = [r for r in results if 'diagnosis' in r]
    scores = [r['diagnosis']['score'] for r in valid]
    avg_score = sum(scores) / len(scores) if scores else 50

    # 按行动分类统计
    actions = {}
    for r in valid:
        a = r['diagnosis']['action']
        actions[a] = actions.get(a, 0) + 1

    # 整体持仓集中度风险
    total_cost = sum(r['cost'] * r['shares'] for r in results)
    concentration = []
    for r in results:
        w = r['cost'] * r['shares'] / total_cost * 100 if total_cost else 0
        if w > 15:
            concentration.append(f"{r['ticker']} 仓位占比{w:.0f}%，集中度偏高")

    # 宏观建议
    macro_advice = []
    exit_count  = actions.get('exit', 0)
    reduce_count= actions.get('reduce', 0)
    if exit_count >= 3:
        macro_advice.append('⚠️ 多只持仓技术面已破位，整体市场偏空，建议降低总仓位')
    if reduce_count >= 5:
        macro_advice.append('📉 超过半数持仓建议减仓，市场承压，保持耐心等待信号')
    if avg_score >= 65:
        macro_advice.append('✅ 整体持仓质量良好，可维持当前配置，关注信号入场机会')

    if not macro_advice:
        macro_advice.append('📊 持仓结构分化，建议聚焦优质高分个股，适当剪除弱势仓位')

    return {
        'avg_score':     round(avg_score, 1),
        'total_count':   len(results),
        'actions':       actions,
        'concentration': concentration,
        'macro_advice':  macro_advice,
        'health_label':  '优秀' if avg_score>=70 else '良好' if avg_score>=55 else '一般' if avg_score>=40 else '偏弱',
        'health_color':  'bullish' if avg_score>=70 else 'neutral' if avg_score>=55 else 'bearish',
    }


def run():
    print("🔍 开始持仓诊断分析...")
    results = []
    for pos in POSITIONS:
        r = analyze_ticker(pos)
        results.append(r)

    overview = generate_portfolio_overview(results)

    output = {
        'generated_at': datetime.now().isoformat(),
        'overview':     overview,
        'stocks':       results,
    }

    for path in [OUTPUT_FILE, ROOT_OUTPUT]:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(output, f, indent=2, default=str)
    print(f"✅ 诊断报告已生成: {len(results)} 只股票")
    return output


if __name__ == '__main__':
    run()
    # 自动 push 到 GitHub Pages
    import subprocess, os
    repo = os.path.join(os.path.dirname(__file__), '..')
    try:
        subprocess.run(['git','add','dashboard/diagnosis.json','diagnosis.json'],
                       cwd=repo, check=True, capture_output=True)
        subprocess.run(['git','commit','-m','auto: 更新持仓诊断报告'],
                       cwd=repo, check=True, capture_output=True)
        subprocess.run(['git','push'], cwd=repo, check=True, capture_output=True)
        print("🚀 已推送到 GitHub Pages")
    except subprocess.CalledProcessError as e:
        if b'nothing to commit' in (e.stdout or b'') + (e.stderr or b''):
            print("  (无变更，跳过 push)")
        else:
            print(f"  push 失败: {e.stderr.decode() if e.stderr else e}")
