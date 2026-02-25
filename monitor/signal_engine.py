"""
信号引擎：扫描股票池，计算买入信号评分
"""
import sys, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, '..')
sys.path.insert(0, '../src')

import yfinance as yf
import pandas as pd
import numpy as np
from analyzer.indicators import add_all_indicators, add_crossover_signals
from datetime import datetime
from config import WATCHLIST, STRATEGY

# 相对强度模块（RS vs SPY）
try:
    from rs_strength import compute_rs_1y
except Exception:
    compute_rs_1y = None


def get_1h_data(ticker: str, days: int = 59) -> pd.DataFrame:
    """拉取1小时K线"""
    from datetime import timedelta
    end = datetime.now()
    start = end - timedelta(days=days)
    # 注意：yfinance 的 end 是“非包含”，用 +1 天避免漏掉当天盘中数据
    df = yf.Ticker(ticker).history(
        start=start.strftime('%Y-%m-%d'),
        end=(end + timedelta(days=1)).strftime('%Y-%m-%d'),
        interval='1h', auto_adjust=True
    )
    if df.empty:
        return df
    df.index = df.index.tz_localize(None) if df.index.tzinfo else df.index
    df.columns = [c.lower() for c in df.columns]
    return add_all_indicators(df)


def check_stabilization(df: pd.DataFrame) -> dict:
    """
    企稳确认：判断股价是否从超卖区回升（而非仍在下跌）
    
    为什么需要？
      纯 RSI<40 的信号会在下跌途中持续触发（接飞刀）。
      真正的好入场点是：RSI 已经从超卖区开始回升，
      说明卖压正在减弱，买力开始介入。
    
    判断条件（满足越多越稳）：
      1. RSI 回升：当前 RSI > 前一根 RSI（动量转正）
      2. 缩量回调：近 5 根 K 的平均量 < 20 日均量（健康洗盘）
      3. K 线收阴但下影线长（有接盘支撑）
      4. 价格未创新低（底部抬高）
    """
    if len(df) < 10:
        return {'confirmed': False, 'score_bonus': 0, 'signals': []}

    signals = []
    bonus = 0

    rsi_curr = float(df['rsi14'].iloc[-1]) if 'rsi14' in df.columns else 50
    rsi_prev = float(df['rsi14'].iloc[-2]) if 'rsi14' in df.columns else 50
    rsi_prev2 = float(df['rsi14'].iloc[-3]) if 'rsi14' in df.columns else 50

    # 1. RSI 企稳回升（连续 2 根上升更可靠）
    if rsi_curr > rsi_prev > rsi_prev2:
        bonus += 8
        signals.append(f'✅ RSI连续回升 ({rsi_prev2:.0f}→{rsi_prev:.0f}→{rsi_curr:.0f})，买力介入')
    elif rsi_curr > rsi_prev:
        bonus += 4
        signals.append(f'⚠️ RSI开始回升 ({rsi_prev:.0f}→{rsi_curr:.0f})，初步企稳')
    else:
        bonus -= 5
        signals.append(f'❌ RSI仍在下行 ({rsi_prev:.0f}→{rsi_curr:.0f})，尚未企稳')

    # 2. 成交量确认（回调缩量 = 健康洗盘）
    if 'volume' in df.columns:
        vol_5avg = float(df['volume'].iloc[-5:].mean())
        vol_20avg = float(df['volume'].iloc[-20:].mean())
        if vol_20avg > 0:
            vol_ratio_5 = vol_5avg / vol_20avg
            if vol_ratio_5 < 0.7:
                bonus += 6
                signals.append(f'✅ 近5根缩量回调({vol_ratio_5:.2f}x)，健康洗盘')
            elif vol_ratio_5 < 1.0:
                bonus += 3
                signals.append(f'⚠️ 量比温和({vol_ratio_5:.2f}x)')
            else:
                signals.append(f'⚠️ 放量下跌({vol_ratio_5:.2f}x)，卖压仍在')

    # 3. 底部抬高（近 3 根低点是否比之前高）
    if 'low' in df.columns and len(df) >= 6:
        recent_low = float(df['low'].iloc[-3:].min())
        prior_low  = float(df['low'].iloc[-6:-3].min())
        if recent_low > prior_low:
            bonus += 5
            signals.append(f'✅ 底部抬高，趋势企稳')

    # 4. K线形态：最后一根是否有下影线（支撑）
    if all(c in df.columns for c in ['open', 'high', 'low', 'close']):
        o = float(df['open'].iloc[-1])
        h = float(df['high'].iloc[-1])
        l = float(df['low'].iloc[-1])
        c = float(df['close'].iloc[-1])
        body = abs(c - o)
        lower_shadow = min(o, c) - l
        if lower_shadow > body * 1.5 and body > 0:
            bonus += 4
            signals.append(f'✅ 长下影线，支撑明显')

    confirmed = bonus >= 5  # 至少有一个正面信号

    return {
        'confirmed': confirmed,
        'score_bonus': max(-5, min(bonus, 20)),  # 上限 +20，下限 -5
        'signals': signals,
    }


def _structure_signals(df: pd.DataFrame, ticker: str) -> dict:
    """Compute structure (1buy/2buy) signals on latest bar.

    Returns dict with keys:
      - structure: { enabled, signals: [..], best: .. }

    This is intentionally separate from score_signal so we can migrate from
    mean-reversion scanning to structure-based execution.
    """
    try:
        import sys as _sys, os as _os
        _sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '../src'))
        from strategy.structure import StructureParams, structure_1buy_signal, structure_2buy_signal

        if df is None or df.empty:
            return {"enabled": True, "signals": [], "best": None}

        i = len(df) - 1
        p = StructureParams()
        s1 = structure_1buy_signal(df, i, p)
        s2 = structure_2buy_signal(df, i, p)

        signals = []
        if s1: signals.append(s1)
        if s2: signals.append(s2)

        # pick best by rr *and* risk distance sanity (prefer reasonable risk)
        best = None
        if signals:
            def key(s):
                risk = max(1e-9, float(s['entry'] - s['sl']))
                risk_pct = risk / float(s['entry'])
                return (1 if risk_pct <= 0.08 else 0, -risk_pct, s.get('type',''))
            best = sorted(signals, key=key, reverse=True)[0]

        return {"enabled": True, "signals": signals, "best": best}
    except Exception:
        return {"enabled": False, "signals": [], "best": None}


def score_signal(row: pd.Series, ticker: str) -> dict:
    """
    对单根K线打分，返回信号评分和详情
    满分100分，≥70分发通知
    """
    score = 0
    details = []
    warnings_list = []

    rsi    = row.get('rsi14', 99)
    bb     = row.get('bb_pct20', 0.5)
    macd_h = row.get('macd_hist', 0)
    vol_r  = row.get('vol_ratio', 1)
    above200 = row.get('above_ma200', 0)
    above50  = row.get('above_ma50', 0)
    above20  = row.get('above_ma20', 0)
    ret5d    = row.get('ret_5d', 0) * 100
    kdj_k    = row.get('kdj_k', 50)
    kdj_j    = row.get('kdj_j', 50)

    # ── 1. MA趋势（30分）──
    if above200:
        score += 30
        details.append('✅ MA200上方（长期趋势向上）')
    elif above50:
        score += 15
        details.append('⚠️ MA50上方但MA200下方（中期趋势）')
        warnings_list.append('未在MA200上方，风险偏高')
    else:
        details.append('❌ MA200/MA50均在上方（下降趋势）')
        warnings_list.append('趋势破位，慎入')

    # ── 2. RSI超卖（30分）──
    if rsi < 25:
        score += 30
        details.append(f'✅ RSI极度超卖 = {rsi:.1f}')
    elif rsi < 32:
        score += 25
        details.append(f'✅ RSI超卖 = {rsi:.1f}')
    elif rsi < 40:
        score += 15
        details.append(f'⚠️ RSI偏低 = {rsi:.1f}')
    elif rsi < 50:
        score += 5
        details.append(f'⚠️ RSI中性 = {rsi:.1f}')
    else:
        details.append(f'❌ RSI偏高 = {rsi:.1f}（未回调）')

    # ── 3. 布林带位置（20分）──
    if bb < 0.10:
        score += 20
        details.append(f'✅ 触碰布林下轨 BB% = {bb:.3f}')
    elif bb < 0.20:
        score += 15
        details.append(f'✅ 接近布林下轨 BB% = {bb:.3f}')
    elif bb < 0.35:
        score += 8
        details.append(f'⚠️ 布林中下区 BB% = {bb:.3f}')
    else:
        details.append(f'❌ 布林偏高 BB% = {bb:.3f}')

    # ── 4. MACD负区（10分）──
    if macd_h < 0:
        score += 10
        details.append(f'✅ MACD负区 = {macd_h:.3f}（回调中）')
    else:
        details.append(f'❌ MACD正区 = {macd_h:.3f}（动能向上，非回调低点）')

    # ── 5. 量比加分（5分）──
    if 0.5 < vol_r < 1.5:
        score += 5
        details.append(f'✅ 量比正常 = {vol_r:.2f}')
    elif vol_r > 2:
        score += 3
        details.append(f'⚠️ 量比偏大 = {vol_r:.2f}（放量，需关注方向）')

    # ── 6. 回调幅度加分（5分）──
    if ret5d < -10:
        score += 5
        details.append(f'✅ 深度回调 5日={ret5d:.1f}%')
    elif ret5d < -5:
        score += 3
        details.append(f'✅ 回调 5日={ret5d:.1f}%')
    elif ret5d > 5:
        warnings_list.append(f'买前5日已涨{ret5d:.1f}%，注意追高风险')

    # ── 7. 企稳确认加权（最多+20分，最多-5分）──
    # 区别：此处用 row 自身数据粗估（企稳检查需要 df，在 phase2_score 层补充）
    # 这里仅做 RSI 方向的单根简单判断
    if rsi < 30 and macd_h > macd_h * 0.95:  # 超卖 + MACD 收窄（动能减弱）
        score += 3
        details.append('⚠️ 初步企稳信号')

    # ── 8. 知识库加权（最多+15分）──
    kb_bonus = 0
    kb_tag = ''
    try:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../jobs'))
        import kb as knowledge_base
        kb_bonus = knowledge_base.score_bonus(ticker)
        if kb_bonus >= 15:
            kb_tag = '⭐ 核心持仓'
            details.append(f'⭐ 核心持仓加权 +{kb_bonus}分')
        elif kb_bonus > 0:
            kb_tag = '🎯 重点关注'
            details.append(f'🎯 重点关注加权 +{kb_bonus}分')
    except Exception:
        pass
    score += kb_bonus

    # ── 9. 相对强度 RS_1Y（vs SPY，新趋势过滤器）──
    rs_1y = -999.0
    if compute_rs_1y is not None:
        try:
            rs_1y = compute_rs_1y(ticker)
        except Exception:
            rs_1y = -999.0

    # RS_1Y 打分：跑赢大盘才有额外分
    if rs_1y > 10:
        score += 10
        details.append(f'✅ 显著跑赢大盘 RS_1Y={rs_1y:+.1f}%')
    elif rs_1y > 0:
        score += 5
        details.append(f'✅ 跑赢大盘 RS_1Y={rs_1y:+.1f}%')
    elif rs_1y > -10:
        details.append(f'⚠️ 略弱于大盘 RS_1Y={rs_1y:+.1f}%')
    else:
        details.append(f'❌ 大幅跑输大盘 RS_1Y={rs_1y:+.1f}%')

    score = min(score, 100)

    # 计算参考止盈止损 + 建议买入价
    price = row.get('close', 0)
    atr   = row.get('atr14', price * 0.05)
    
    # 止盈止损（方案B：强趋势用更大的止盈目标）
    is_strong = score >= STRATEGY.get('strong_trend_min_score', 85)
    tp_pct = STRATEGY['take_profit_strong'] if is_strong else STRATEGY['take_profit']
    sl_pct = STRATEGY['stop_loss_strong']  if is_strong else STRATEGY['stop_loss']

    tp_price = round(price * (1 + tp_pct), 2)
    sl_price = round(price * (1 + sl_pct), 2)
    rr_ratio = tp_pct / abs(sl_pct)

    tp_label = f"+{int(tp_pct*100)}%" if float(tp_pct*100).is_integer() else f"+{tp_pct*100:.0f}%"
    sl_label = f"{int(sl_pct*100)}%" if float(sl_pct*100).is_integer() else f"{sl_pct*100:.0f}%"
    mode_label = '强趋势' if is_strong else '普通'
    
    # 建议买入价（根据回调深度和RSI位置）
    ma20 = row.get('ma20', price)
    ma50 = row.get('ma50', price)
    bb_lower = ma20 - 2 * (ma20 * 0.02)  # 估算布林下轨
    
    if rsi < 25:
        # 极度超卖，建议立即入场
        suggest_price = round(price * 1.005, 2)  # +0.5% 追一点
        suggest_note = "极度超卖，建议市价入场"
    elif rsi < 35 and bb < 0.2:
        # 深度回调，建议现价或略低
        suggest_price = round(price * 0.995, 2)  # -0.5% 挂单
        suggest_note = "深度回调，可挂单略低于现价"
    elif price < ma20 * 0.98:
        # 在MA20下方，建议等回踩MA20
        suggest_price = round(ma20 * 0.995, 2)
        suggest_note = f"等待回踩MA20 (${ma20:.2f}) 附近"
    elif price < ma50 * 0.98:
        # 在MA50下方，建议等回踩MA50
        suggest_price = round(ma50 * 0.995, 2)
        suggest_note = f"等待回踩MA50 (${ma50:.2f}) 附近"
    else:
        # 正常回调，建议现价
        suggest_price = round(price * 0.99, 2)
        suggest_note = "回调中，可挂单略低于现价"
    
    # 重新计算基于建议价的止盈止损（使用同一套强趋势参数）
    tp_price_suggest = round(suggest_price * (1 + tp_pct), 2)
    sl_price_suggest = round(suggest_price * (1 + sl_pct), 2)

    return {
        'ticker':    ticker,
        'score':     score,
        'kb_tag':    kb_tag,
        'price':     round(price, 2),
        'suggest_price': suggest_price,
        'suggest_note': suggest_note,
        'rsi14':     round(rsi, 1),
        'bb_pct':    round(bb, 3),
        'macd_hist': round(macd_h, 4),
        'above_ma200': bool(above200),
        'above_ma50':  bool(above50),
        'vol_ratio':   round(vol_r, 2),
        'ret_5d':      round(ret5d, 1),
        'tp_price':    tp_price_suggest,
        'sl_price':    sl_price_suggest,
        'rr_ratio':    round(rr_ratio, 2),
        'tp_label':    f"{mode_label} {tp_label}",
        'sl_label':    f"{mode_label} {sl_label}",
        'risk_mode':   'strong' if is_strong else 'normal',
        'details':     details,
        'warnings':    warnings_list,
        'scan_time':   datetime.now().strftime('%Y-%m-%d %H:%M'),
        'bar_time':    row.name.strftime('%Y-%m-%d %H:%M') if getattr(row, 'name', None) is not None else None,
        'bar_close':   round(price, 2),
        'price_source': '1H_bar_close',
        'rs_1y':       rs_1y,
    }


def format_signal_message(sig: dict) -> str:
    """格式化 Telegram 通知消息"""
    score = sig['score']
    ticker = sig['ticker']

    # 评分 → emoji
    if score >= 85:
        level = '🔥 强烈信号'
        emoji = '🚀'
    elif score >= 70:
        level = '✅ 买入信号'
        emoji = '🎯'
    else:
        level = '⚠️ 关注信号'
        emoji = '👀'

    ma_status = '✅ MA200上方' if sig['above_ma200'] else ('⚠️ MA50上方' if sig['above_ma50'] else '❌ 均线下方')

    kb_tag_str = f"  {sig.get('kb_tag', '')}\n" if sig.get('kb_tag') else ''
    # 会话标注（北京时间粗略映射美股盘前/盘中/盘后）
    def _session_bj(ts: str) -> str:
        try:
            from datetime import datetime, time
            dt = datetime.strptime(ts, '%Y-%m-%d %H:%M')
            t = dt.time()
            if time(16,0) <= t < time(21,30):
                return '盘前'
            if t >= time(21,30) or t < time(4,0):
                return '盘中'
            if time(4,0) <= t < time(8,0):
                return '盘后'
            return '休市'
        except Exception:
            return ''

    sess = _session_bj(sig.get('scan_time',''))
    sess_tag = f"（{sess}）" if sess else ''

    # 触发K线/会话信息放到最底部备注（不打断阅读）
    bar_t = sig.get('bar_time')
    note_parts = []
    if sess:
        note_parts.append(sess)
    if bar_t:
        note_parts.append(f"触发1H收盘@{bar_t}")
    note = f"\n\n备注: {'｜'.join(note_parts)}" if note_parts else ''

    # 标的行不再重复“强烈/买入”等级（等级信息放到 title）
    msg = f"""{emoji} **{ticker}**
━━━━━━━━━━━━━━━━━━
{kb_tag_str}📊 评分: {score}/100
💰 当前价: ${sig['price']}
⏰ 时间: {sig['scan_time']} (北京){sess_tag}

📈 技术指标:
  RSI14: {sig['rsi14']}  |  BB%: {sig['bb_pct']}
  MACD柱: {sig['macd_hist']}  |  量比: {sig['vol_ratio']}
  趋势: {ma_status}
  5日涨跌: {sig['ret_5d']:+.1f}%

🎯 参考出场:
  止盈: ${sig['tp_price']} ({sig.get('tp_label','')})
  止损: ${sig['sl_price']} ({sig.get('sl_label','')})
  盈亏比: {sig['rr_ratio']}:1"""

    if sig['warnings']:
        msg += '\n\n⚠️ 风险提示:\n' + '\n'.join(f'  • {w}' for w in sig['warnings'])

    msg += '\n\n_仅供参考，请结合基本面和市场环境判断_'
    msg += note
    return msg


def run_scan(watchlist: list = None) -> list:
    """执行一次完整扫描，返回所有触发信号"""
    if watchlist is None:
        watchlist = WATCHLIST

    if not watchlist:
        print("⚠️  股票池为空，请在 config.py 的 WATCHLIST 中添加股票")
        return []

    print(f"\n🔍 扫描 {len(watchlist)} 只股票 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    signals = []
    errors  = []

    for ticker in watchlist:
        try:
            df = get_1h_data(ticker)
            if len(df) < 30:
                errors.append(f"{ticker}: 数据不足")
                continue

            row = df.iloc[-1]
            sig = score_signal(row, ticker)

            status = f"  {ticker:<6} 评分={sig['score']:>3}  RSI={sig['rsi14']:>5.1f}  BB%={sig['bb_pct']:>6.3f}  MA200={'✅' if sig['above_ma200'] else '❌'}"
            if sig['score'] >= 70:
                status += ' ← 🔔 触发!'
            print(status)

            if sig['score'] >= 70:
                signals.append(sig)

        except Exception as e:
            errors.append(f"{ticker}: {e}")

    print(f"\n  ✅ 扫描完成  触发信号: {len(signals)} 只  错误: {len(errors)} 只")
    if errors:
        for e in errors[:5]:
            print(f"  ✗ {e}")

    return signals


if __name__ == '__main__':
    sigs = run_scan()
    if sigs:
        print(f"\n{'='*60}")
        print("📨 待发送信号:")
        for s in sigs:
            print(f"\n{format_signal_message(s)}")
