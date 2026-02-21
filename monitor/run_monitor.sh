#!/bin/bash
# 由 OpenClaw cron 调用
# 扫描股票池，有信号时输出格式化文本供 OpenClaw 发送 TG

cd "$(dirname "$0")/.." || exit 1
source venv/bin/activate

python3 monitor/scan_once.py 2>/dev/null
