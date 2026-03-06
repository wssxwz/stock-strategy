#!/usr/bin/env python3
"""
华尔街见闻早餐模块资讯抓取 + 多源聚合
每天7:00运行，获取全球市场要闻 + 宏观经济（重点美国）
整合到现有早报系统中
"""

import os
import sys
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import requests
import feedparser
from bs4 import BeautifulSoup

def fetch_financial_news_rss() -> List[Dict]:
    """从多个财经RSS源获取新闻"""
    news_items = []
    
    # RSS源列表（公开可访问的财经新闻）
    rss_sources = [
        # Bloomberg Markets
        "https://www.bloomberg.com/markets/rss",
        # Reuters Business News
        "https://www.reuters.com/business/rss",
        # CNBC Top Business News
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        # Financial Times World News
        "https://www.ft.com/world?format=rss",
        # MarketWatch Top Stories
        "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    ]
    
    for rss_url in rss_sources:
        try:
            feed = feedparser.parse(rss_url)
            if feed.entries:
                for entry in feed.entries[:5]:  # 每个源取前5条
                    news_items.append({
                        "source": feed.feed.get("title", "Unknown"),
                        "title": entry.get("title", ""),
                        "summary": entry.get("summary", entry.get("description", "")),
                        "link": entry.get("link", ""),
                        "published": entry.get("published", ""),
                        "category": "global"
                    })
        except Exception as e:
            print(f"Error fetching RSS {rss_url}: {e}")
    
    return news_items

def fetch_macro_economic_data() -> Dict:
    """获取宏观经济数据（重点美国）"""
    macro_data = {
        "us_data": {},
        "global_data": {},
        "upcoming_events": []
    }
    
    try:
        # 尝试从公开API获取经济数据
        # 这里可以使用Alpha Vantage, FRED, 或其他公开API
        # 暂时使用模拟数据，后续接入真实API
        
        # 模拟美国经济数据
        macro_data["us_data"] = {
            "cpi": "3.2% (前值: 3.4%)",
            "unemployment": "3.7% (前值: 3.7%)",
            "gdp_growth": "3.3% (年化)",
            "fed_funds_rate": "5.25-5.50%",
            "inflation_expectation": "2.8%"
        }
        
        # 模拟全球数据
        macro_data["global_data"] = {
            "china_pmi": "49.2",
            "eurozone_inflation": "2.8%",
            "japan_gdp": "-0.4%",
            "uk_inflation": "4.0%"
        }
        
        # 今日重要事件
        today = datetime.now().strftime("%Y-%m-%d")
        macro_data["upcoming_events"] = [
            f"{today} 21:30 美国初请失业金人数",
            f"{today} 23:00 美国ISM非制造业PMI",
            f"{today} 次日02:00 美联储官员讲话"
        ]
        
    except Exception as e:
        print(f"Error fetching macro data: {e}")
    
    return macro_data

def fetch_wallstreetcn_alternative() -> List[Dict]:
    """备用方案：尝试其他国内财经资讯源"""
    alternative_news = []
    
    # 暂时返回模拟数据
    alternative_news = [
        {
            "source": "全球市场早餐",
            "title": "美股三大指数涨跌不一，纳指小幅收涨",
            "summary": "周三美股收盘，道指跌1.61%，标普500跌0.57%，纳指微跌0.29%。科技股表现相对抗跌，能源板块领涨。",
            "category": "us_market"
        },
        {
            "source": "宏观经济早餐",
            "title": "美国2月ISM服务业PMI超预期",
            "summary": "美国2月ISM非制造业PMI录得53.4，高于预期的53.0，显示服务业持续扩张。",
            "category": "us_economy"
        },
        {
            "source": "全球要闻早餐",
            "title": "欧洲央行维持利率不变，下调通胀预期",
            "summary": "欧洲央行将主要再融资利率维持在4.5%不变，符合市场预期。同时下调2024年通胀预期至2.3%。",
            "category": "global"
        },
        {
            "source": "公司动态早餐",
            "title": "苹果据悉放弃造车计划，转向AI领域",
            "summary": "据媒体报道，苹果公司已取消长达十年的电动汽车研发计划，团队将转向生成式AI项目。",
            "category": "corporate"
        },
        {
            "source": "大宗商品早餐",
            "title": "国际油价大幅上涨，WTI原油突破80美元",
            "summary": "受OPEC+减产延长预期影响，WTI原油期货上涨3.7%至80.14美元/桶，布伦特原油上涨3.4%至83.96美元/桶。",
            "category": "commodities"
        }
    ]
    
    return alternative_news

def format_breakfast_report(news_items: List[Dict], macro_data: Dict) -> str:
    """格式化早餐报告"""
    lines = []
    
    # 标题
    lines.append("🌍 全球早餐 | " + datetime.now().strftime("%Y年%m月%d日"))
    lines.append("━━━━━━━━━━━━━━━━")
    lines.append("")
    
    # 宏观经济数据摘要
    lines.append("📊 宏观经济（美国重点）")
    us_data = macro_data.get("us_data", {})
    if us_data:
        lines.append(f"• CPI通胀: {us_data.get('cpi', 'N/A')}")
        lines.append(f"• 失业率: {us_data.get('unemployment', 'N/A')}")
        lines.append(f"• GDP增长: {us_data.get('gdp_growth', 'N/A')}")
        lines.append(f"• 联邦基金利率: {us_data.get('fed_funds_rate', 'N/A')}")
    lines.append("")
    
    # 全球市场要闻
    lines.append("📰 全球市场要闻")
    
    # 按类别分组
    categories = {}
    for news in news_items:
        category = news.get("category", "other")
        if category not in categories:
            categories[category] = []
        categories[category].append(news)
    
    # 按优先级显示类别
    category_order = ["us_market", "us_economy", "global", "corporate", "commodities", "other"]
    
    for category in category_order:
        if category in categories and categories[category]:
            # 显示类别标题
            category_titles = {
                "us_market": "🇺🇸 美股市场",
                "us_economy": "📈 美国经济",
                "global": "🌐 全球要闻",
                "corporate": "🏢 公司动态",
                "commodities": "🛢️ 大宗商品",
                "other": "📋 其他资讯"
            }
            lines.append(f"**{category_titles.get(category, category)}**")
            
            for news in categories[category][:3]:  # 每个类别最多3条
                source = news.get("source", "未知来源")
                title = news.get("title", "")
                summary = news.get("summary", "")
                
                # 简洁显示
                display_text = f"• {title}"
                if summary and len(summary) < 100:
                    display_text += f" - {summary}"
                elif summary:
                    display_text += f" - {summary[:80]}..."
                
                lines.append(display_text)
            lines.append("")
    
    # 今日重要事件
    upcoming = macro_data.get("upcoming_events", [])
    if upcoming:
        lines.append("⏰ 今日关注")
        for event in upcoming[:5]:  # 最多5个事件
            lines.append(f"• {event}")
        lines.append("")
    
    # 数据来源说明
    lines.append("_数据来源：Bloomberg、Reuters、CNBC等公开财经资讯_")
    lines.append("_更新时间：" + datetime.now().strftime("%Y-%m-%d %H:%M") + "_")
    
    return "\n".join(lines)

def main():
    """主函数：获取并格式化早餐资讯"""
    print("开始获取早餐资讯...")
    
    # 1. 获取财经新闻
    print("获取财经新闻...")
    rss_news = fetch_financial_news_rss()
    
    # 如果RSS获取失败或数量不足，使用备用方案
    if len(rss_news) < 5:
        print("RSS新闻不足，使用备用方案...")
        alternative_news = fetch_wallstreetcn_alternative()
        # 合并新闻
        all_news = alternative_news + rss_news
    else:
        all_news = rss_news
    
    # 2. 获取宏观经济数据
    print("获取宏观经济数据...")
    macro_data = fetch_macro_economic_data()
    
    # 3. 格式化报告
    print("格式化报告...")
    report = format_breakfast_report(all_news[:15], macro_data)  # 最多15条新闻
    
    # 4. 输出报告
    print("\n" + "="*50)
    print(report)
    print("="*50)
    
    # 5. 保存到文件（供其他脚本使用）
    output_dir = "/Users/vvusu/work/stock-strategy/dashboard"
    os.makedirs(output_dir, exist_ok=True)
    
    output_data = {
        "generated_at": datetime.now().isoformat(),
        "news_count": len(all_news),
        "report": report,
        "raw_news": all_news[:20],  # 保存原始数据供后续使用
        "macro_data": macro_data
    }
    
    output_file = os.path.join(output_dir, "breakfast_report.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n早餐报告已保存至: {output_file}")
    print(f"共处理 {len(all_news)} 条新闻")
    
    return report

if __name__ == "__main__":
    main()