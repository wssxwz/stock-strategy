#!/bin/bash
# 启动检查脚本 - 在cron任务开始时运行

set -e

echo "🔍 交易系统启动检查..."
echo "================================"

# 1. 检查虚拟环境
if [ ! -f "venv/bin/activate" ]; then
    echo "❌ 虚拟环境不存在"
    echo "请运行: python3 -m venv venv"
    exit 1
fi
echo "✅ 虚拟环境存在"

# 2. 激活虚拟环境
source venv/bin/activate
echo "✅ 虚拟环境已激活"

# 3. 检查Python版本
python_version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "✅ Python版本: $python_version"

# 4. 检查依赖
echo "📦 检查依赖..."
python3 check_dependencies.py

# 5. 检查环境变量
if [ -f ".env" ]; then
    echo "✅ 找到.env文件"
    source .env 2>/dev/null || true
elif [ -f "../.secrets/env/stock-strategy.live.env" ]; then
    echo "✅ 找到实盘环境文件"
    source ../.secrets/env/stock-strategy.live.env 2>/dev/null || true
else
    echo "⚠️  未找到环境文件，使用默认值"
fi

# 6. 检查必要目录
for dir in "logs" "data/trades" "dashboard"; do
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
        echo "✅ 创建目录: $dir"
    else
        echo "✅ 目录存在: $dir"
    fi
done

echo "================================"
echo "✅ 启动检查完成，系统就绪"
