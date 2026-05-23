#!/usr/bin/env python3
"""
短剧热点监控脚本
- 获取短剧热度榜 Top30
- 获取抖音热搜并筛选短剧相关
- 搜索行业动态
- 生成结构化日报
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

# ============ 配置 ============
SHORTDRAMA_API = "https://api.kuleu.com/api/shortdramarank"
DOUYIN_HOT_API = "https://v2.xxapi.cn/api/douyinhot"
DEFAULT_REPORT_DIR = r"D:\视频生产\reports\shortdrama"

# 短剧直接相关关键词
SHORTDRAMA_KEYWORDS = [
    "短剧", "微短剧", "竖屏剧", "迷你剧",
]

# 影视/剧集相关关键词（更泛化的筛选）
DRAMA_RELATED_KEYWORDS = [
    "剧", "开播", "追剧", "热播", "定档",
    "霸总", "甜宠", "逆袭", "重生",
    "虐恋", "穿越", "古装", "仙侠",
    "番外", "续集", "大结局",
]


def fetch_json(url, timeout=15):
    """获取JSON API数据"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[ERROR] 请求 {url} 失败: {e}", file=sys.stderr)
        return None


def fetch_shortdrama_rank():
    """获取短剧热度榜"""
    data = fetch_json(SHORTDRAMA_API)
    if not data or data.get("code") != 200:
        print("[WARN] 短剧热度榜API返回异常", file=sys.stderr)
        return []
    return data.get("data", [])


def fetch_douyin_hot():
    """获取抖音热搜并筛选短剧相关词条"""
    data = fetch_json(DOUYIN_HOT_API)
    if not data or data.get("code") != 200:
        print("[WARN] 抖音热搜API返回异常", file=sys.stderr)
        return []
    
    all_items = data.get("data", [])
    shortdrama_items = []
    drama_items = []
    
    for item in all_items:
        word = item.get("word", "")
        entry = {
            "position": item.get("position", 0),
            "word": word,
            "hot_value": item.get("hot_value", 0),
            "label": item.get("label", 0),
        }
        # 优先匹配短剧直接关键词
        if any(kw in word for kw in SHORTDRAMA_KEYWORDS):
            shortdrama_items.append(entry)
        # 其次匹配影视/剧集相关关键词（排除明显不相关的：如"剧毒"、"剧烈"等）
        elif any(kw in word for kw in DRAMA_RELATED_KEYWORDS):
            # 排除误匹配
            if not any(neg in word for neg in ["剧毒", "剧烈", "剧增", "剧集剧"]):
                drama_items.append(entry)
    
    return shortdrama_items + drama_items


def classify_genre(title):
    """根据剧名简单分类题材"""
    # 注意：匹配顺序影响分类优先级，越具体的越靠前
    genre_map = {
        "霸总": ["总裁", "霸总", "首富", "CEO", "豪门", "先生是个狠"],
        "婚恋": ["婚", "妻", "夫", "领证", "闪婚", "新婚", "宠妻", "备孕", "婚约"],
        "甜宠": ["甜", "宠", "恋", "爱", "娇", "吻", "上瘾", "只对她"],
        "逆袭": ["逆袭", "翻身", "崛起", "无敌", "巅峰", "摊牌", "不好惹", "战将"],
        "重生": ["重生", "回到", "穿越", "前世", "八零"],
        "古装": ["皇", "帝", "妃", "宫", "朝", "侯", "将军", "古装", "太子", "主母"],
        "复仇": ["复仇", "报仇", "复仇者", "血债", "恩断"],
        "悬疑": ["谜", "案", "侦探", "真相", "谍", "查案", "秘密"],
        "战神": ["战龙", "战神", "枭雄", "修仙", "化神"],
        "逆袭/翻盘": ["离婚", "出狱", "撤资", "逃出"],
    }
    
    genres = []
    for genre, keywords in genre_map.items():
        if any(kw in title for kw in keywords):
            genres.append(genre)
    
    return genres if genres else ["其他"]


def generate_genre_stats(rank_data):
    """统计题材分布"""
    genre_count = {}
    for item in rank_data:
        title = item.get("title", "")
        genres = classify_genre(title)
        for g in genres:
            genre_count[g] = genre_count.get(g, 0) + 1
    return genre_count


def format_hot_value(hot_str):
    """格式化热度值"""
    try:
        return str(hot_str)
    except:
        return str(hot_str)


def generate_report(rank_data, douyin_data, genre_stats, include_analysis=True):
    """生成Markdown日报"""
    now = datetime.now()
    date_str = now.strftime("%Y年%m月%d日")
    date_file = now.strftime("%Y-%m-%d")
    
    lines = []
    lines.append(f"# 短剧热点日报 - {date_str}\n")
    lines.append(f"> 生成时间: {now.strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # === 短剧热度榜 ===
    lines.append("## 🔥 短剧热度榜 Top15\n")
    lines.append("| 排名 | 剧名 | 热度 |")
    lines.append("|:----:|------|-----:|")
    
    top15 = rank_data[:15] if rank_data else []
    for item in top15:
        rank = item.get("ranking", "-")
        title = item.get("title", "-")
        hots = item.get("hots", "-")
        lines.append(f"| {rank} | {title} | {hots} |")
    lines.append("")
    
    # === 完整Top30 ===
    if len(rank_data) > 15:
        lines.append("<details>")
        lines.append("<summary>📊 查看完整 Top30</summary>\n")
        lines.append("| 排名 | 剧名 | 热度 |")
        lines.append("|:----:|------|-----:|")
        for item in rank_data:
            rank = item.get("ranking", "-")
            title = item.get("title", "-")
            hots = item.get("hots", "-")
            lines.append(f"| {rank} | {title} | {hots} |")
        lines.append("")
        lines.append("</details>\n")
    
    # === 抖音短剧热搜 ===
    if douyin_data:
        lines.append("## 📱 抖音短剧相关热搜\n")
        lines.append("| 排名 | 词条 | 热度值 |")
        lines.append("|:----:|------|-------:|")
        for item in douyin_data:
            pos = item.get("position", "-")
            word = item.get("word", "-")
            hot = item.get("hot_value", 0)
            # 格式化热度
            if hot >= 10000:
                hot_str = f"{hot/10000:.1f}w"
            else:
                hot_str = str(hot)
            lines.append(f"| {pos} | {word} | {hot_str} |")
        lines.append("")
    else:
        lines.append("## 📱 抖音短剧相关热搜\n")
        lines.append("> 今日抖音热搜中暂无短剧相关词条\n")
    
    # === 题材分布 ===
    if genre_stats:
        lines.append("## 📈 题材分布\n")
        total = sum(genre_stats.values())
        lines.append("| 题材 | 数量 | 占比 |")
        lines.append("|------|:----:|-----:|")
        # 按数量排序
        for genre, count in sorted(genre_stats.items(), key=lambda x: -x[1]):
            pct = f"{count/total*100:.1f}%"
            lines.append(f"| {genre} | {count} | {pct} |")
        lines.append("")
    
    # === 选题参考 ===
    if include_analysis and rank_data:
        lines.append("## 💡 选题参考\n")
        
        # 找最热题材
        top_genre = max(genre_stats.items(), key=lambda x: x[1]) if genre_stats else ("未知", 0)
        top3_titles = [item.get("title", "") for item in rank_data[:3]]
        
        lines.append(f"基于今日热度数据分析：\n")
        lines.append(f"1. **最热题材**: {top_genre[0]}类短剧（{top_genre[1]}部上榜），建议优先关注")
        lines.append(f"2. **头部剧目**: {'、'.join(top3_titles)} 持续领跑，可做对标分析")
        
        # 冷门机会
        cold_genres = [g for g, c in genre_stats.items() if c == 1 and g != "其他"]
        if cold_genres:
            lines.append(f"3. **差异化机会**: {'、'.join(cold_genres)} 题材竞品少，可考虑切入")
        
        lines.append(f"4. **抖音热搜联动**: 抖音当前有 {len(douyin_data)} 条短剧相关热搜，可结合热搜做选题")
        lines.append("")
    
    return "\n".join(lines), date_file


def save_report(content, date_file, output_dir=None):
    """保存报告到文件"""
    report_dir = Path(output_dir) if output_dir else Path(DEFAULT_REPORT_DIR)
    report_dir.mkdir(parents=True, exist_ok=True)
    
    filename = f"短剧热点日报_{date_file}.md"
    filepath = report_dir / filename
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    
    return str(filepath)


def print_summary(rank_data, douyin_data, genre_stats):
    """打印控制台摘要"""
    print("\n" + "=" * 60)
    print("  短剧热点监控 - 数据摘要")
    print("=" * 60)
    
    print(f"\n🔥 短剧热度榜 Top5:")
    for item in rank_data[:5]:
        rank = item.get("ranking", "-")
        title = item.get("title", "-")
        hots = item.get("hots", "-")
        print(f"  {rank}. {title}  (热度: {hots})")
    
    if douyin_data:
        print(f"\n📱 抖音短剧热搜 ({len(douyin_data)}条):")
        for item in douyin_data[:5]:
            print(f"  #{item.get('position', '-')} {item.get('word', '-')} (热度: {item.get('hot_value', 0)})")
    else:
        print("\n📱 抖音短剧热搜: 无相关词条")
    
    if genre_stats:
        print(f"\n📈 题材分布:")
        for genre, count in sorted(genre_stats.items(), key=lambda x: -x[1])[:5]:
            print(f"  {genre}: {count}部")
    
    print("\n" + "=" * 60)


def main():
    # 解析参数
    args = set(sys.argv[1:])
    rank_only = "--rank-only" in args
    gen_report = "--report" in args
    output_dir = None
    
    # 解析 --output 参数
    for i, arg in enumerate(sys.argv):
        if arg == "--output" and i + 1 < len(sys.argv):
            output_dir = sys.argv[i + 1]
    
    # 1. 获取短剧热度榜
    print("[1/3] 获取短剧热度榜...")
    rank_data = fetch_shortdrama_rank()
    if not rank_data:
        print("[ERROR] 未能获取短剧热度榜数据，退出", file=sys.stderr)
        sys.exit(1)
    print(f"  ✓ 获取到 {len(rank_data)} 条短剧排名数据")
    
    # 2. 获取抖音热搜
    douyin_data = []
    if not rank_only:
        print("[2/3] 获取抖音热搜...")
        douyin_data = fetch_douyin_hot()
        print(f"  ✓ 抖音热搜中筛选出 {len(douyin_data)} 条短剧相关词条")
    else:
        print("[2/3] 跳过抖音热搜（--rank-only 模式）")
    
    # 3. 统计题材分布
    print("[3/3] 统计题材分布...")
    genre_stats = generate_genre_stats(rank_data)
    print(f"  ✓ 识别到 {len(genre_stats)} 种题材类型")
    
    # 打印摘要
    print_summary(rank_data, douyin_data, genre_stats)
    
    # 生成报告
    if gen_report:
        content, date_file = generate_report(rank_data, douyin_data, genre_stats, include_analysis=True)
        filepath = save_report(content, date_file, output_dir)
        print(f"\n📄 报告已保存: {filepath}")
    else:
        # 即使不生成文件报告，也输出简要结果
        content, date_file = generate_report(rank_data, douyin_data, genre_stats, include_analysis=True)
        # 输出JSON格式供skill解析
        result = {
            "rank_data": rank_data,
            "douyin_data": douyin_data,
            "genre_stats": genre_stats,
            "report_content": content,
            "date": date_file,
        }
        print("\n---JSON_OUTPUT---")
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
