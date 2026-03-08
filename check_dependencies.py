#!/usr/bin/env python3
"""
依赖检查脚本 - 在运行任何交易脚本前检查
"""
import sys

REQUIRED_PACKAGES = [
    'yfinance',
    'pandas',
    'numpy',
    'requests',
    'alpha_vantage',
    'bs4',  # beautifulsoup4 的实际包名
    'lxml',
    'feedparser'
]

def check_package(package):
    """检查包是否已安装"""
    try:
        __import__(package)
        return True, f"✅ {package}"
    except ImportError:
        return False, f"❌ {package} 未安装"

def main():
    print("🔍 检查交易系统依赖...")
    print("=" * 50)
    
    all_ok = True
    results = []
    
    for package in REQUIRED_PACKAGES:
        ok, msg = check_package(package)
        results.append(msg)
        if not ok:
            all_ok = False
    
    # 打印结果
    for result in results:
        print(result)
    
    print("=" * 50)
    
    if not all_ok:
        print("\n🚨 缺少依赖！请运行以下命令安装：")
        print(f"cd {sys.path[0]}")
        print("source venv/bin/activate")
        missing = [p for p in REQUIRED_PACKAGES if not check_package(p)[0]]
        print(f"pip install {' '.join(missing)}")
        sys.exit(1)
    else:
        print("✅ 所有依赖已安装")
        sys.exit(0)

if __name__ == "__main__":
    main()
