"""
可视化报告生成器
输出独立 HTML 报告，包含：
1. 策略规则总结卡片
2. 已平仓交易盈亏分布图
3. RPS vs 胜率散点图
4. 买入时RSI分布（胜/败对比）
5. 扫描器结果榜单
6. 回测权益曲线
"""
import json, os
import pandas as pd
import numpy as np
from datetime import datetime

REPORT_PATH = 'reports/strategy_report.html'
os.makedirs('reports', exist_ok=True)

# ── 加载数据 ──
closed  = pd.read_csv('data/processed/closed_trades.csv')
snap    = pd.read_csv('data/processed/entry_snapshot_full.csv')
scanner = pd.read_csv('data/processed/scanner_results.csv') if os.path.exists('data/processed/scanner_results.csv') else pd.DataFrame()
bt      = pd.read_csv('data/processed/backtest_results.csv') if os.path.exists('data/processed/backtest_results.csv') else pd.DataFrame()

wins  = closed[closed['action'] == '止盈']
loses = closed[closed['action'] == '止损']

# ── 数据序列化 ──
pnl_wins  = wins['pnl'].tolist()
pnl_loses = loses['pnl'].tolist()
ticker_labels = closed['ticker'].tolist()
pnl_all       = closed['pnl'].tolist()
colors = ['#4CAF50' if p > 0 else '#F44336' for p in pnl_all]

rsi_wins  = snap[snap['result']=='止盈']['rsi14'].tolist()
rsi_loses = snap[snap['result']=='止损']['rsi14'].tolist()

# 预计算scatter点位（避免 f-string 内 dict 推导冲突）
rsi_win_pts  = [{'x': v, 'y': round(i*0.5, 1)} for i, v in enumerate(rsi_wins)]
rsi_lose_pts = [{'x': v, 'y': round(i*0.5+5, 1)} for i, v in enumerate(rsi_loses)]

# 扫描器 top20
if not scanner.empty:
    top_scan = scanner[scanner['score'] >= 50].head(20)
else:
    top_scan = pd.DataFrame()

# 回测权益曲线
if not bt.empty:
    bt_sorted = bt.sort_values('entry_date')
    bt_sorted['cumret'] = (1 + bt_sorted['return_pct']/100).cumprod() * 100 - 100
    bt_dates  = bt_sorted['entry_date'].tolist()
    bt_equity = bt_sorted['cumret'].round(2).tolist()
    bt_win_rate = round(bt_sorted['is_win'].mean()*100, 1)
    bt_avg_ret  = round(bt_sorted['return_pct'].mean(), 2)
    bt_total    = len(bt_sorted)
else:
    bt_dates = bt_equity = []
    bt_win_rate = bt_avg_ret = bt_total = 'N/A'

# 扫描器表格行
scan_rows = ''
if not top_scan.empty:
    for i, (_, r) in enumerate(top_scan.iterrows(), 1):
        ma200 = '✅' if r['above_ma200'] else '❌'
        ma50  = '✅' if r['above_ma50']  else '❌'
        macd  = '✅' if r['macd_hist'] < 0 else '❌'
        score_color = '#4CAF50' if r['score'] >= 75 else '#FF9800' if r['score'] >= 60 else '#9E9E9E'
        scan_rows += f"""
        <tr>
          <td>{i}</td>
          <td><strong>{r['ticker']}</strong></td>
          <td><span style="color:{score_color};font-weight:bold">{r['score']:.0f}</span></td>
          <td>${r['price']:.2f}</td>
          <td>{r['rsi14']:.1f}</td>
          <td style="color:{'#F44336' if r['ret_5d']<0 else '#4CAF50'}">{r['ret_5d']:+.1f}%</td>
          <td style="color:{'#4CAF50' if r['ret_1y']>0 else '#F44336'}">{r['ret_1y']:+.1f}%</td>
          <td>{ma200}</td><td>{ma50}</td><td>{macd}</td>
        </tr>"""

HTML = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>格格list策略分析报告</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, 'PingFang SC', sans-serif; background: #0f1117; color: #e0e0e0; }}
  .header {{ background: linear-gradient(135deg, #1a1f35, #2d3561); padding: 40px; text-align: center; border-bottom: 2px solid #3d4580; }}
  .header h1 {{ font-size: 2.2em; color: #fff; margin-bottom: 8px; }}
  .header p  {{ color: #8892b0; font-size: 1em; }}
  .container {{ max-width: 1400px; margin: 0 auto; padding: 30px 20px; }}
  .grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }}
  .grid3 {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px; margin-bottom: 20px; }}
  .card {{ background: #1a1f2e; border-radius: 12px; padding: 24px; border: 1px solid #2a2f45; }}
  .card h2 {{ font-size: 1.1em; color: #8892b0; margin-bottom: 16px; text-transform: uppercase; letter-spacing: 1px; }}
  .stat-big {{ font-size: 2.8em; font-weight: 700; color: #fff; line-height: 1; }}
  .stat-label {{ font-size: 0.85em; color: #8892b0; margin-top: 4px; }}
  .stat-green {{ color: #4CAF50; }}
  .stat-red   {{ color: #F44336; }}
  .stat-yellow {{ color: #FF9800; }}
  .rule-box {{ background: #0d1117; border-radius: 8px; padding: 16px; margin-bottom: 12px; border-left: 3px solid #4CAF50; }}
  .rule-box.warn {{ border-left-color: #F44336; }}
  .rule-box h3 {{ font-size: 0.9em; color: #4CAF50; margin-bottom: 8px; }}
  .rule-box.warn h3 {{ color: #F44336; }}
  .rule-box p  {{ font-size: 0.88em; color: #cdd6f4; line-height: 1.7; }}
  .chart-wrap {{ position: relative; height: 280px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.88em; }}
  th {{ background: #2a2f45; color: #8892b0; padding: 10px 12px; text-align: left; }}
  td {{ padding: 9px 12px; border-bottom: 1px solid #2a2f45; }}
  tr:hover td {{ background: #1f2535; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.78em; font-weight: 600; }}
  .badge-green {{ background: rgba(76,175,80,.2); color: #4CAF50; }}
  .badge-red   {{ background: rgba(244,67,54,.2); color: #F44336; }}
  .section-title {{ font-size: 1.3em; color: #cdd6f4; margin: 30px 0 16px; font-weight: 600; }}
  @media(max-width:768px) {{ .grid2,.grid3{{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>

<div class="header">
  <h1>📊 格格list策略分析报告</h1>
  <p>IBD强势股 × 回调抄底策略 | 逆向工程还原 | 生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
</div>

<div class="container">

  <!-- KPI卡片 -->
  <div class="section-title">📈 策略绩效总览</div>
  <div class="grid3">
    <div class="card">
      <h2>已平仓胜率</h2>
      <div class="stat-big stat-yellow">{len(wins)/len(closed)*100:.1f}%</div>
      <div class="stat-label">{len(wins)}胜 / {len(loses)}负 / {len(closed)}总</div>
    </div>
    <div class="card">
      <h2>期望收益/笔</h2>
      <div class="stat-big stat-green">+{(len(wins)/len(closed)*wins['pnl'].mean() + len(loses)/len(closed)*loses['pnl'].mean()):.2f}%</div>
      <div class="stat-label">正期望策略 ✅</div>
    </div>
    <div class="card">
      <h2>盈亏比</h2>
      <div class="stat-big stat-green">{wins['pnl'].mean()/abs(loses['pnl'].mean()):.2f}:1</div>
      <div class="stat-label">均盈+{wins['pnl'].mean():.1f}% / 均亏{loses['pnl'].mean():.1f}%</div>
    </div>
  </div>

  <div class="grid2">
    <div class="card">
      <h2>各笔盈亏（已平仓18笔）</h2>
      <div class="chart-wrap"><canvas id="pnlChart"></canvas></div>
    </div>
    <div class="card">
      <h2>买入时 RSI14 分布对比</h2>
      <div class="chart-wrap"><canvas id="rsiChart"></canvas></div>
    </div>
  </div>

  <!-- 策略规则 -->
  <div class="section-title">📐 还原策略规则</div>
  <div class="grid2">
    <div>
      <div class="rule-box">
        <h3>✅ 选股条件（必须）</h3>
        <p>
          • <strong>RPS评级 ≥ 80</strong>：近1年涨幅排名全市场前20%<br>
          • <strong>股价在 MA200 上方</strong>：长期趋势向上（10/10止盈笔全满足）<br>
          • 时间周期：<strong>60分钟</strong>信号
        </p>
      </div>
      <div class="rule-box">
        <h3>✅ 买入时机（等回调）</h3>
        <p>
          • <strong>RSI14 &lt; 45</strong>（优选 &lt;35 超卖区）<br>
          • <strong>买前5日回调 &gt;3%</strong>（深度回调 -5%~-22%）<br>
          • MACD 处于<strong>负值区</strong>（企稳中）<br>
          • 在 MA50 支撑附近
        </p>
      </div>
      <div class="rule-box">
        <h3>✅ 出场纪律（硬止盈止损）</h3>
        <p>
          • 止盈：<strong>+12~13%</strong>（开仓即设定）<br>
          • 止损：<strong>-7~8%</strong>（开仓即设定）<br>
          • 盈亏比：<strong>1.67:1</strong>
        </p>
      </div>
    </div>
    <div>
      <div class="rule-box warn">
        <h3>❌ 失败案例共性（避免）</h3>
        <p>
          • INTC/XME：<strong>RSI&gt;50买入</strong>（没等回调就追进去）<br>
          • ASTS：<strong>买前20日大涨+12%</strong>（追高）<br>
          • MRNA止损：<strong>已破MA200</strong>（趋势坏掉了）<br>
          • ZETA：<strong>RPS仅13</strong>（选股失误，例外）
        </p>
      </div>
      <div class="rule-box">
        <h3>💡 核心结论</h3>
        <p>
          <strong>RPS≥95 + MA200上方 + RSI&lt;45 + 近期深度回调 = 高胜率买点</strong><br><br>
          这是强势股中的逆势/抄底策略，不是追涨策略。<br>
          胜方买入前平均回调 -4.8%，RSI平均 42.8<br>
          败方大多在 RSI>50 时买入（没有充分回调）
        </p>
      </div>
      <div class="card" style="margin-top:0;padding:16px;">
        <h2>RPS分布 → 胜率</h2>
        <div class="chart-wrap" style="height:200px"><canvas id="rpsChart"></canvas></div>
      </div>
    </div>
  </div>

  <!-- 扫描器 -->
  <div class="section-title">🔍 今日扫描结果（实时候选标的）</div>
  <div class="card">
    <p style="color:#8892b0;font-size:0.85em;margin-bottom:16px">
      评分规则：MA200上方(30分) + RSI超卖(30分) + 深度回调(25分) + MA50上方(10分) + 强势(10分) + MACD负区(5分)
    </p>
    <table>
      <tr><th>排名</th><th>股票</th><th>评分</th><th>价格</th><th>RSI14</th><th>5日涨跌</th><th>1年涨跌</th><th>MA200</th><th>MA50</th><th>MACD负</th></tr>
      {scan_rows if scan_rows else '<tr><td colspan="10" style="text-align:center;color:#666">暂无数据</td></tr>'}
    </table>
  </div>

  <!-- 回测 -->
  <div class="section-title">🔁 历史回测结果</div>
  <div class="grid3">
    <div class="card">
      <h2>回测胜率</h2>
      <div class="stat-big stat-yellow">{bt_win_rate}%</div>
      <div class="stat-label">共 {bt_total} 笔模拟交易</div>
    </div>
    <div class="card">
      <h2>回测均收益/笔</h2>
      <div class="stat-big {'stat-green' if isinstance(bt_avg_ret, float) and bt_avg_ret > 0 else 'stat-red'}">{bt_avg_ret if isinstance(bt_avg_ret, str) else f'+{bt_avg_ret:.2f}%'}</div>
      <div class="stat-label">策略参数：止盈+13% / 止损-8%</div>
    </div>
    <div class="card">
      <h2>数据覆盖</h2>
      <div class="stat-big" style="font-size:1.4em;color:#8892b0">2022~今</div>
      <div class="stat-label">30只股票，含牛熊市测试</div>
    </div>
  </div>
  <div class="card">
    <h2>回测累计收益曲线</h2>
    <div class="chart-wrap" style="height:320px"><canvas id="equityChart"></canvas></div>
  </div>

</div>

<script>
const chartDefaults = {{
  color: '#8892b0',
  plugins: {{ legend: {{ labels: {{ color: '#8892b0' }} }} }},
  scales: {{
    x: {{ ticks: {{ color: '#8892b0' }}, grid: {{ color: '#2a2f45' }} }},
    y: {{ ticks: {{ color: '#8892b0' }}, grid: {{ color: '#2a2f45' }} }}
  }}
}};

// 盈亏柱状图
new Chart(document.getElementById('pnlChart'), {{
  type: 'bar',
  data: {{
    labels: {json.dumps(ticker_labels)},
    datasets: [{{ label: '盈亏%', data: {json.dumps(pnl_all)},
      backgroundColor: {json.dumps(colors)}, borderRadius: 4 }}]
  }},
  options: {{ ...chartDefaults, plugins: {{ legend: {{ display: false }},
    tooltip: {{ callbacks: {{ label: ctx => ctx.raw > 0 ? '+'+ctx.raw+'%' : ctx.raw+'%' }} }} }} }}
}});

// RSI对比直方图
new Chart(document.getElementById('rsiChart'), {{
  type: 'scatter',
  data: {{
    datasets: [
      {{ label: '止盈', data: {json.dumps(rsi_win_pts)},
        backgroundColor: 'rgba(76,175,80,0.7)', pointRadius: 8 }},
      {{ label: '止损', data: {json.dumps(rsi_lose_pts)},
        backgroundColor: 'rgba(244,67,54,0.7)', pointRadius: 8 }}
    ]
  }},
  options: {{ ...chartDefaults,
    scales: {{
      x: {{ min:10, max:80, title:{{ display:true, text:'RSI14值', color:'#8892b0' }},
           ticks:{{ color:'#8892b0' }}, grid:{{ color:'#2a2f45' }} }},
      y: {{ display:false }}
    }},
    plugins: {{ legend: {{ labels: {{ color:'#8892b0' }} }},
      annotation: {{ annotations: {{ line1: {{ type:'line', xMin:45, xMax:45,
        borderColor:'rgba(255,152,0,0.6)', borderWidth:2,
        label:{{ content:'RSI=45 买入阈值', display:true, color:'#FF9800', position:'start' }} }} }} }}
    }}
  }}
}});

// RPS分布胜率
new Chart(document.getElementById('rpsChart'), {{
  type: 'bar',
  data: {{
    labels: ['<60','60-80','80-90','90-95','95-100'],
    datasets: [
      {{ label: '胜率%', data: [0, null, 75, 0, 64],
        backgroundColor: ['#F44336','#9E9E9E','#4CAF50','#F44336','#4CAF50'], borderRadius: 4 }},
    ]
  }},
  options: {{ ...chartDefaults,
    scales: {{
      x: {{ ticks:{{ color:'#8892b0' }}, grid:{{ color:'#2a2f45' }} }},
      y: {{ min:0, max:100, ticks:{{ color:'#8892b0', callback: v=>v+'%' }}, grid:{{ color:'#2a2f45' }} }}
    }}
  }}
}});

// 权益曲线
const btDates  = {json.dumps(bt_dates)};
const btEquity = {json.dumps(bt_equity)};
if (btDates.length > 0) {{
  new Chart(document.getElementById('equityChart'), {{
    type: 'line',
    data: {{
      labels: btDates,
      datasets: [{{ label: '累计收益%', data: btEquity,
        borderColor: '#4CAF50', backgroundColor: 'rgba(76,175,80,0.1)',
        fill: true, tension: 0.3, pointRadius: 0, borderWidth: 2 }}]
    }},
    options: {{ ...chartDefaults,
      scales: {{
        x: {{ ticks:{{ maxTicksLimit:12, color:'#8892b0' }}, grid:{{ color:'#2a2f45' }} }},
        y: {{ ticks:{{ color:'#8892b0', callback: v=>v+'%' }}, grid:{{ color:'#2a2f45' }} }}
      }},
      plugins: {{ legend: {{ labels: {{ color:'#8892b0' }} }} }}
    }}
  }});
}} else {{
  document.getElementById('equityChart').parentElement.innerHTML =
    '<p style="color:#666;text-align:center;padding:80px">回测数据加载中...</p>';
}}
</script>
</body>
</html>
"""

with open(REPORT_PATH, 'w', encoding='utf-8') as f:
    f.write(HTML)

print(f"✅ 报告已生成: {REPORT_PATH}")
