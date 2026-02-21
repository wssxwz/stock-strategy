"""
策略逆向工程核心模块
从交易记录中挖掘买入/卖出规则
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.tree import DecisionTreeClassifier, export_text
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import cross_val_score
import warnings
warnings.filterwarnings('ignore')


# ==================== 特征选择 ====================
ENTRY_FEATURES = [
    # 趋势
    'entry_above_ma20', 'entry_above_ma50', 'entry_above_ma200',
    'entry_ma20_slope',
    # 动量
    'entry_rsi14', 'entry_rsi6',
    'entry_macd', 'entry_macd_hist', 'entry_macd_cross',
    # 位置
    'entry_bb_pct20', 'entry_bb_width20',
    'entry_pct_from_52w_high', 'entry_pct_from_52w_low',
    # 量价
    'entry_vol_ratio',
    # 短期价格动量
    'entry_ret_1d', 'entry_ret_3d', 'entry_ret_5d', 'entry_ret_10d',
    # 波动
    'entry_atr_pct14',
    # K线
    'entry_body_ratio', 'entry_is_gap_up', 'entry_is_gap_down',
    # KDJ
    'entry_kdj_k', 'entry_kdj_d', 'entry_kdj_j',
]


def select_available_features(df: pd.DataFrame, feature_list: list) -> list:
    """过滤掉不存在的列"""
    return [f for f in feature_list if f in df.columns]


# ==================== 条件统计分析 ====================
def analyze_entry_conditions(enriched_df: pd.DataFrame) -> pd.DataFrame:
    """
    统计买入时刻的技术指标分布
    找出买入信号的共性条件
    """
    features = select_available_features(enriched_df, ENTRY_FEATURES)
    if not features:
        print("⚠️ 没有可用的技术特征，请先 enrich_trades")
        return pd.DataFrame()

    df = enriched_df[features + ['is_win', 'return_pct', 'hold_days']].copy()
    df = df.dropna(subset=features)

    result = []
    for feat in features:
        col = df[feat]
        result.append({
            'feature':    feat,
            'all_mean':   round(col.mean(), 4),
            'win_mean':   round(col[df['is_win']].mean(), 4) if df['is_win'].any() else None,
            'loss_mean':  round(col[~df['is_win']].mean(), 4) if (~df['is_win']).any() else None,
            'all_median': round(col.median(), 4),
        })

    return pd.DataFrame(result).sort_values('feature')


# ==================== 决策树找规则 ====================
def find_entry_rules(enriched_df: pd.DataFrame,
                     max_depth: int = 4,
                     min_samples: int = 3) -> str:
    """
    用决策树提取可解释的买入规则
    """
    features = select_available_features(enriched_df, ENTRY_FEATURES)
    df = enriched_df[features + ['is_win']].dropna()

    if len(df) < 10:
        return "❌ 样本量太少，无法训练"

    X = df[features]
    y = df['is_win'].astype(int)

    clf = DecisionTreeClassifier(
        max_depth=max_depth,
        min_samples_leaf=min_samples,
        random_state=42
    )
    clf.fit(X, y)

    rules = export_text(clf, feature_names=features, max_depth=max_depth)
    score = cross_val_score(clf, X, y, cv=min(5, len(df)), scoring='accuracy').mean()

    print(f"\n📊 决策树准确率: {score:.1%} (交叉验证)")
    print(f"样本量: {len(df)} 笔交易, 胜率: {y.mean():.1%}\n")
    print("决策树规则:\n" + "="*60)
    print(rules)

    return rules


# ==================== 特征重要性 ====================
def feature_importance(enriched_df: pd.DataFrame) -> pd.DataFrame:
    """
    RandomForest 特征重要性排名
    找出哪些指标最能区分盈亏
    """
    features = select_available_features(enriched_df, ENTRY_FEATURES)
    df = enriched_df[features + ['is_win']].dropna()

    if len(df) < 10:
        print("❌ 样本量太少")
        return pd.DataFrame()

    X = df[features]
    y = df['is_win'].astype(int)

    rf = RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1)
    rf.fit(X, y)

    imp = pd.DataFrame({
        'feature':    features,
        'importance': rf.feature_importances_
    }).sort_values('importance', ascending=False)

    print("\n🔑 最重要的买入指标 (Top 15):")
    print(imp.head(15).to_string(index=False))

    return imp


# ==================== 持仓时间分析 ====================
def analyze_hold_days(enriched_df: pd.DataFrame) -> dict:
    """分析持仓时间分布，判断是短线/中线/长线"""
    if 'hold_days' not in enriched_df.columns:
        return {}

    hd = enriched_df['hold_days'].dropna()
    result = {
        'mean':   round(hd.mean(), 1),
        'median': round(hd.median(), 1),
        'min':    int(hd.min()),
        'max':    int(hd.max()),
        'p25':    round(hd.quantile(0.25), 1),
        'p75':    round(hd.quantile(0.75), 1),
    }

    # 风格判断
    med = result['median']
    if med <= 3:
        style = '超短线 (隔日/T+2)'
    elif med <= 10:
        style = '短线 (1~2周)'
    elif med <= 30:
        style = '中短线 (1~4周)'
    elif med <= 90:
        style = '中线 (1~3月)'
    else:
        style = '长线 (3月以上)'

    result['style'] = style
    print(f"\n⏱️ 持仓风格: {style}")
    print(f"   中位数: {result['median']} 天, 均值: {result['mean']} 天")
    return result


# ==================== 止盈止损分析 ====================
def analyze_exit_rules(enriched_df: pd.DataFrame) -> dict:
    """从盈亏数据推断止盈止损位设置"""
    if 'return_pct' not in enriched_df.columns:
        return {}

    wins  = enriched_df[enriched_df['is_win']]['return_pct']
    loses = enriched_df[~enriched_df['is_win']]['return_pct']

    result = {}
    if len(wins):
        result['take_profit_median'] = round(wins.median(), 2)
        result['take_profit_p75']    = round(wins.quantile(0.75), 2)
        result['take_profit_max']    = round(wins.max(), 2)

    if len(loses):
        result['stop_loss_median'] = round(loses.median(), 2)
        result['stop_loss_p25']    = round(loses.quantile(0.25), 2)
        result['stop_loss_max']    = round(loses.min(), 2)

    if result:
        print(f"\n🎯 推断止盈止损:")
        if 'take_profit_median' in result:
            print(f"   止盈中位: +{result['take_profit_median']}%  上四分位: +{result['take_profit_p75']}%")
        if 'stop_loss_median' in result:
            print(f"   止损中位: {result['stop_loss_median']}%  下四分位: {result['stop_loss_p25']}%")

    return result


# ==================== 综合报告 ====================
def full_analysis(enriched_df: pd.DataFrame) -> dict:
    """一键运行全套分析"""
    print("=" * 60)
    print("📋 交易策略逆向工程分析报告")
    print("=" * 60)

    report = {}

    print("\n[1/4] 持仓风格分析...")
    report['hold_style'] = analyze_hold_days(enriched_df)

    print("\n[2/4] 止盈止损分析...")
    report['exit_rules'] = analyze_exit_rules(enriched_df)

    print("\n[3/4] 特征重要性分析...")
    report['feature_importance'] = feature_importance(enriched_df)

    print("\n[4/4] 决策树规则提取...")
    report['decision_tree'] = find_entry_rules(enriched_df)

    return report
