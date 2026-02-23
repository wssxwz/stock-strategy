"""
核心持仓快照生成器
生成 core_holdings.json 供 Dashboard 读取
在 morning_brief.py 里调用，每天早上更新
"""
import warnings
warnings.filterwarnings('ignore')

import yfinance as yf
import json, os
from datetime import datetime

DASHBOARD_DIR = os.path.join(os.path.dirname(__file__), '../dashboard')
OUTPUT_FILE   = os.path.join(DASHBOARD_DIR, 'core_holdings.json')
ROOT_OUTPUT   = os.path.join(os.path.dirname(__file__), '../core_holdings.json')

CORE_TICKERS = [
    # Tier 1 核心持仓
    'TSLA','META','CRWD','PANW','ORCL','RKLB','OKLO','SOUN','SNOW',
    'ARM','AMD','NNE','SOFI','DXYZ','ASTS','NBIS','IONQ',
    # 常用参考
    'GOOGL','NVDA',
]


def get_core_snapshot() -> dict:
    result = {}
    for t in CORE_TICKERS:
        try:
            tk   = yf.Ticker(t)
            hist = tk.history(period='5d', interval='1d')
            if len(hist) < 1:
                continue
            last      = hist.iloc[-1]
            prev      = hist.iloc[-2] if len(hist) >= 2 else last
            close     = float(last['Close'])
            prev_close= float(prev['Close'])
            chg       = close - prev_close
            chg_pct   = chg / prev_close * 100
            date_str  = hist.index[-1].strftime('%Y-%m-%d')
            vol       = int(last['Volume'])

            # 52 周高低（用于展示位置）
            info      = tk.fast_info
            high52    = float(getattr(info, 'year_high', 0) or 0)
            low52     = float(getattr(info, 'year_low',  0) or 0)

            # 距 52 周高点的距离
            off_high  = ((close - high52) / high52 * 100) if high52 else None

            result[t] = {
                'ticker':     t,
                'price':      round(close, 2),
                'change':     round(chg, 2),
                'change_pct': round(chg_pct, 2),
                'date':       date_str,
                'volume':     vol,
                'high_52w':   round(high52, 2) if high52 else None,
                'low_52w':    round(low52,  2) if low52  else None,
                'off_high':   round(off_high, 1) if off_high else None,
            }
        except Exception as e:
            print(f"  {t} 获取失败: {e}")

    return {
        'tickers':      result,
        'generated_at': datetime.now().isoformat(),
    }


def run():
    print("⭐ 更新核心持仓快照...")
    snap = get_core_snapshot()
    for t, d in snap['tickers'].items():
        print(f"  {t}: ${d['price']} ({d['change_pct']:+.2f}%) on {d['date']}")

    for path in [OUTPUT_FILE, ROOT_OUTPUT]:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(snap, f, indent=2)
    print(f"  ✅ 已写入 core_holdings.json")
    return snap


if __name__ == '__main__':
    run()
