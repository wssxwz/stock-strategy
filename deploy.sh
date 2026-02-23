#!/bin/bash
# 部署脚本 — 每次改完 dashboard/ 后执行
set -e
echo "📦 同步前端文件..."
cp dashboard/index.html index.html
cp dashboard/app.js     app.js

echo "📦 同步数据文件..."
cp dashboard/calendar.json       calendar.json       2>/dev/null || true
cp dashboard/weekly_reports.json weekly_reports.json 2>/dev/null || true
cp dashboard/signals.json        signals.json        2>/dev/null || true
cp dashboard/diagnosis.json      diagnosis.json      2>/dev/null || true
cp dashboard/core_holdings.json  core_holdings.json  2>/dev/null || true
cp dashboard/push_history.json   push_history.json   2>/dev/null || true

MSG=${1:-"update: dashboard sync"}
echo "🚀 提交推送: $MSG"
git add -A
git commit -m "$MSG" 2>/dev/null || echo "  (无变更)"
git push

echo "✅ 完成！等待 GitHub Pages 更新 (~2分钟)"
echo "   https://wssxwz.github.io/stock-strategy/"
