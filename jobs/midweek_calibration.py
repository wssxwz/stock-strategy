"""周中策略校准（周三 20:00 北京）

定位：5分钟读完，回答三件事：
1) 本周主线（risk-on/off、风格）
2) 板块轮动（强弱）
3) 本周后半段执行纪律（该追/该等/该减压）

输出：MIDWEEK_START ~ MIDWEEK_END
"""

import sys, os, warnings
warnings.filterwarnings('ignore')

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime
from market_data import get_batch_quotes, get_fear_greed, get_sector_performance, INDICES


def run():
    now = datetime.now()
    date_str = now.strftime('%-m月%-d日') if hasattr(now, 'strftime') else now.strftime('%m月%d日')

    idx = get_batch_quotes(list(INDICES.keys()))
    fg = get_fear_greed()
    sects = get_sector_performance() or {}

    def fmt(pct):
        try:
            pct=float(pct)
        except Exception:
            pct=0.0
        return f"{('+' if pct>=0 else '')}{pct:.2f}%"

    spy = idx.get('^GSPC',{}).get('change_pct',0)
    qqq = idx.get('^NDX',{}).get('change_pct',0)
    dia = idx.get('DIA',{}).get('change_pct',0)

    # simple style read
    style = '偏风险规避' if qqq < spy - 0.3 else ('偏风险偏好' if qqq > spy + 0.3 else '轮动/震荡')

    lines = [
        f"📌 周中策略校准 | {date_str}（周三）",
        "━━━━━━━━━━━━━━━━",
        f"\n一、本周主线（到目前为止）",
        f"• SPY {fmt(spy)}｜QQQ {fmt(qqq)}｜DIA {fmt(dia)}｜风格：{style}",
        f"• 情绪：{fg.get('emoji','')} {fg.get('label_zh','')} {fg.get('value','-')}（0=极恐 100=极贪）",
    ]

    if sects:
        sl=list(sects.items())
        top=sl[:3]
        bot=sl[-3:]
        lines += [
            f"\n二、板块轮动（强→弱）",
            "• 强：" + '，'.join([f"{d['name']}{fmt(d['change_pct'])}" for _,d in top]),
            "• 弱：" + '，'.join([f"{d['name']}{fmt(d['change_pct'])}" for _,d in bot]),
        ]

    lines += [
        f"\n三、后半周执行纪律",
        "• 只做两类：STRUCT（结构+MA200+ATR低）/ MR（BB%<0.10）",
        "• 其余一律不追：等回撤、等结构确认、等风险下降",
        "• 盘前21:00看局势，盘中按小时扫描（强信号单推，普通汇总）",
        "\n_仅供参考_",
    ]

    msg='\n'.join(lines)
    print('MIDWEEK_START')
    print(msg)
    print('MIDWEEK_END')


if __name__ == '__main__':
    run()
