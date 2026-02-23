"""合并线上已有的单条 buy_signal 为 1 条 buy_signal_batch"""
import json, os
from datetime import datetime

# 读取线上 push_history
import urllib.request
url = 'https://wssxwz.github.io/stock-strategy/push_history.json'
data = json.load(urllib.request.urlopen(url))

# 分离单条和批次
single_signals = [d for d in data if d.get('type') == 'buy_signal']
batch_records = [d for d in data if d.get('type') == 'buy_signal_batch']

print(f"单条信号：{len(single_signals)}条")
print(f"批次记录：{len(batch_records)}条")

if not single_signals:
    print("无需合并")
    exit()

# 按时间分组（同一天的合并）
from collections import defaultdict
groups = defaultdict(list)
for s in single_signals:
    date = s.get('time', '')[:10]  # YYYY-MM-DD
    groups[date].append(s)

print(f"\n按日期分组：{list(groups.keys())}")

# 为每个日期创建 1 条批次记录
new_batches = []
for date, signals in groups.items():
    # 提取原始 Telegram 原文（raw 字段）
    raw_msgs = [s.get('raw', s.get('content', '')) for s in signals]
    batch_raw = "\n\n".join(raw_msgs)
    
    # 统计
    buy_count = len(signals)
    strong_count = sum(1 for s in signals if '强' in s.get('title', '') or '9' in s.get('title', '')[-2:] or '8' in s.get('title', '')[-2:])
    
    batch_title = f"📣 全市场扫描信号（{date} 北京）"
    batch_summary = f"✅ 买入 {buy_count} / 卖出 0｜强趋势 {strong_count} 只"
    
    new_batches.append({
        'id': f"batch_merged_{date}",
        'type': 'buy_signal_batch',
        'title': batch_title,
        'summary': batch_summary,
        'content': batch_summary,
        'raw': batch_raw,
        'time': f"{date} {signals[0].get('time', '').split(' ')[1] if ' ' in signals[0].get('time', '') else '12:00'}",
        'signal_count': buy_count,
        'strong_count': strong_count,
        'merged_from': len(signals),
    })

print(f"\n生成 {len(new_batches)} 条批次记录")

# 合并所有记录（新批次 + 旧批次，去掉单条）
merged = new_batches + batch_records
# 按时间排序（最新在前）
merged.sort(key=lambda x: x.get('time', ''), reverse=True)

print(f"最终记录数：{len(merged)}条")

# 写回本地
base = 'dashboard'
for path in [f'{base}/push_history.json', 'push_history.json']:
    with open(path, 'w') as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print(f"✅ 已写入 {path}")

print("\n下一步：运行 deploy.sh 推送到 GitHub Pages")
