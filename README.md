# Stock Strategy Reverse Engineering

从交易记录逆向还原交易策略的工具。

## 项目结构

```
stock-strategy/
├── analyze.py              # 主入口
├── data/
│   ├── raw/               # 原始数据（交易记录 + 股票OHLCV）
│   └── processed/         # 处理后数据
├── reports/               # 分析报告
├── src/
│   ├── fetcher/
│   │   └── market_data.py # yfinance 数据拉取
│   ├── analyzer/
│   │   ├── indicators.py  # 技术指标计算
│   │   └── trade_parser.py# 交易记录解析 + 指标快照
│   └── strategy/
│       └── reverse_engineer.py  # 逆向工程核心
└── notebooks/             # Jupyter 探索性分析
```

## 快速使用

```bash
# 激活环境
source venv/bin/activate

# 测试框架（示例数据）
python analyze.py

# 使用真实交易记录
python analyze.py data/raw/trades.csv
```

## 交易记录格式

CSV 文件，支持以下列：

| 列名 | 说明 | 必填 |
|------|------|------|
| ticker | 股票代码 (如 AAPL) | ✅ |
| entry_date | 买入日期 (YYYY-MM-DD) | ✅ |
| entry_price | 买入价格 | ✅ |
| exit_date | 卖出日期 | ✅ |
| exit_price | 卖出价格 | ✅ |
| return_pct | 收益率 (%) | 可选，自动计算 |
| exit_type | 止盈/止损 | 可选 |
| note | 备注 | 可选 |

## 分析流程

1. **解析交易记录** → 标准化格式
2. **拉取市场数据** → yfinance 自动获取 OHLCV
3. **计算技术指标** → MA/EMA/MACD/RSI/KDJ/BB/ATR等
4. **快照合并** → 在每笔买入/卖出时刻提取指标值
5. **逆向分析**：
   - 持仓风格识别（超短线/中线/长线）
   - 止盈止损区间推断
   - 特征重要性排名（RandomForest）
   - 决策树规则提取（可解释规则）
