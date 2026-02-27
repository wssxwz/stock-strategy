# Strategy Versions (追溯记录)

> 说明：这是“交易策略/信号引擎”迭代的版本化记录（便于复盘、回测对齐、回滚）。
> 版本命名以 **信号生成与过滤逻辑** 为主（不包含纯展示/UI 文案微调）。

---

## V1 — Baseline MR Scoring（基础均值回归打分版）

**核心定位**：以 MR（均值回归）为主的 1H 信号打分，评分≥阈值触发推送，TP/SL 固定比例。

**主要逻辑**
- `monitor/signal_engine.py::score_signal()`：
  - 趋势（MA200/MA50）
  - RSI 超卖分层
  - BB%（bb_pct20）分层加分
  - MACD/量比/5日回调 ret_5d 加权
  - 输出：score + 参考止盈止损（普通/强趋势两套）
- `monitor/full_scan.py`：
  - Phase1 日线快速过滤 + Phase2 1H 评分
  - 过滤链路：score≥阈值（含市场 regime 动态阈值）

**风险管理**
- TP/SL：普通（+13%/-8%），强趋势更大 TP（+20%）

**里程碑/参考提交（近似）**
- `01f0dc8` 起：加入更保守的 knife/chop/trend 识别元信息（回测 meta）

---

## V2 — 数据稳定 + 结构体系灰度 + RS_1Y/ret5 等增强（策略增强版）

**核心定位**：在不破坏 MR 主流程的前提下，补齐数据稳定性、回测/结构体系，并把一些关键过滤/加权改为更稳的策略增强。

**主要增强**
1) **数据稳定性（1H 本地 store）**
- `src/data_store.py`：1H start/end 拉空时 fallback `period=730d`（clamp 730d）
- `jobs/backtest_strategy.py`：长周期回测优先走本地 store，减少 yfinance None 导致的批量跳票

2) **结构交易体系（灰度展示 + 回测对比）**
- 新增 `src/strategy/structure.py`：一买/二买（breakout→pullback→confirm）
- 回测支持：`entry_mode = mean_reversion | structure_1buy | structure_2buy`
- 扫描消息灰度展示结构信号：不改变原 MR 触发，仅在消息末尾展示 1buy/2buy（tag）

3) **RS_1Y 口径与 ret5 动态降级**
- RS_1Y：从硬门槛改为更软的“极弱过滤 + 评分项”（默认只过滤 rs_1y <= -10%）
- ret5：全市场无信号 streak 降级（L0 -3%、L1 -2.5%、L2 -2%）

**里程碑/参考提交（摘取关键）**
- `7062b94`：data_store 1h backfill fallback（period fetch）
- `6837fd6`：回测长周期优先走本地 store
- `b555a36`/`02c867c`：结构模块 + 回测 entry_mode
- `3f06c50`/`d66ecfe`：结构信号灰度展示 + RS_1Y 接入

---

## V3 — BB% Gate 分层硬门槛 + Signals 字段补齐（策略过滤升级版）

**核心定位**：把历史模拟中最强解释变量（BB%超卖甜蜜区）变成硬过滤；同时把 signals.json 的关键指标字段补齐并对历史回填，方便持续做分档统计与策略追溯。

**BB% gate（更稳方案，已上线）**
- **Normal/MR 入场（strict）**：要求 `bb_pct < 0.10`
- **Strong trend 入场（relaxed）**：允许 `bb_pct < 0.25`，但必须同时满足：
  - `score >= 85` 且 `above_ma200 == True`

落点：`monitor/full_scan.py` 过滤链路新增一层：
- 原始触发 → ret5通过 → **BB过滤** → 达到阈值

**Signals 字段补齐（schema_version=2）**
- `dashboard/export_signals.py`：新增保存字段
  - `macd_hist, vol_ratio, ret_5d, above_ma200, above_ma50, rr_ratio, risk_mode, rs_1y` 等
- 新增回填脚本：`jobs/backfill_signals_fields.py`
  - 用本地 1H store 对历史 signals 回填缺失字段

**里程碑提交**
- `88b00f2`：signals 字段补齐 + 历史回填 + BB% gate（strict/relaxed）

---

## 版本使用建议（用于回测/复盘对齐）
- 做历史复盘时：记录使用的版本号（V1/V2/V3）+ 当天配置（阈值、ret5 level、regime）。
- 做策略优化时：优先在 V3 上做参数搜索（bb gate / rsi gate / ret5 gate / rs_1y gate）。
