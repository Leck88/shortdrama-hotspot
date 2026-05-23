#!/usr/bin/env python3
"""
短剧热点监控脚本 v4.1 (Shortdrama Hotspot Monitor)

改进点（相比 v4.0）：
1. 使用 config.py 集中管理配置，消除硬编码路径
2. 使用 utils.genre 共享题材分类，消除重复代码
3. 使用 utils.api_helpers 带重试+缓存的请求，提升稳定性
4. 使用 logging 替代 print，支持日志级别控制
5. 修复 --comfyui 参数未生效的 bug
6. 使用 argparse 替代手动 sys.argv 解析

功能概述：
1. 获取短剧热度排行榜 Top30 —— 调用酷乐免费API，获取当日最新短剧热度排名
2. 获取抖音热搜并筛选短剧相关词条 —— 调用小小API获取抖音热搜，用关键词匹配筛选短剧/影视相关内容
3. 题材自动分类 —— 根据剧名关键词，将短剧归类为婚恋、霸总、甜宠、逆袭等10种题材
4. 生成结构化日报 —— 输出Markdown格式报告，包含热度榜、抖音热搜、题材分布、选题参考

使用方式：
  python fetch_hotspot.py                        # 控制台查看摘要，输出JSON
  python fetch_hotspot.py --report               # 生成Markdown日报文件
  python fetch_hotspot.py --rank-only            # 仅获取热度榜，跳过抖音热搜
  python fetch_hotspot.py --output ./reports      # 指定报告输出目录
  python fetch_hotspot.py --script --comfyui     # 生成剧本 + ComfyUI配置
  python fetch_hotspot.py --script --genre 霸总  # 指定题材生成剧本
  python fetch_hotspot.py --script --batch       # 批量生成5个剧本

数据源说明：
  - 短剧热度榜：https://api.kuleu.com/api/shortdramarank （免费，无需Key，每日更新30条）
  - 抖音热搜：https://v2.xxapi.cn/api/douyinhot （免费，无需Key，实时更新）

依赖：核心功能无第三方依赖，仅使用 Python 3 标准库
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# 项目内部模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import config
from utils.genre import classify_genre
from utils.api_helpers import fetch_json_with_retry

# 日志配置
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format=config.LOG_FORMAT,
)
logger = logging.getLogger("shortdrama.hotspot")

# ============ 关键词配置 ============
# 短剧直接相关关键词 —— 用于从抖音热搜中精确匹配短剧类词条
SHORTDRAMA_KEYWORDS = [
    "短剧", "微短剧", "竖屏剧", "迷你剧",
]

# 影视/剧集相关关键词 —— 更泛化的筛选，匹配开播、追剧、热播等影视相关词条
DRAMA_RELATED_KEYWORDS = [
    "剧", "开播", "追剧", "热播", "定档",
    "霸总", "甜宠", "逆袭", "重生",
    "虐恋", "穿越", "古装", "仙侠",
    "番外", "续集", "大结局",
]

# ============ 数据获取函数 ============
def fetch_shortdrama_rank():
    """
    获取短剧热度排行榜

    调用酷乐API获取当日Top30短剧排名数据。
    每条数据包含：ranking（排名）、title（剧名）、hots（热度值，如"212.3w"）

    返回：
        列表，每项为字典 {"ranking": 1, "title": "剧名", "hots": "212.3w"}
        请求失败返回空列表
    """
    data = fetch_json_with_retry(
        config.SHORTDRAMA_API,
        timeout=config.API_TIMEOUT,
        max_retries=config.API_MAX_RETRIES,
        retry_delay=config.API_RETRY_DELAY,
        cache_dir=str(config.CACHE_DIR),
        cache_expire_minutes=config.CACHE_EXPIRE_MINUTES,
    )
    if not data or data.get("code") != 200:
        logger.warning("短剧热度榜API返回异常")
        return []
    return data.get("data", [])


def fetch_douyin_hot():
    """
    获取抖音热搜并筛选短剧相关词条

    工作流程：
        1. 调用抖音热搜API获取全站热搜数据
        2. 用SHORTDRAMA_KEYWORDS精确匹配短剧类词条（优先）
        3. 用DRAMA_RELATED_KEYWORDS泛化匹配影视相关词条（其次）
        4. 排除误匹配（如"剧毒"、"剧烈"等含"剧"字但非剧集的词条）
        5. 合并返回，短剧直接相关的排在前面

    返回：
        列表，每项为字典 {"position": 排名, "word": 词条, "hot_value": 热度值, "label": 标签}
        无匹配结果返回空列表
    """
    data = fetch_json_with_retry(
        config.DOUYIN_HOT_API,
        timeout=config.API_TIMEOUT,
        max_retries=config.API_MAX_RETRIES,
        retry_delay=config.API_RETRY_DELAY,
        cache_dir=str(config.CACHE_DIR),
        cache_expire_minutes=config.CACHE_EXPIRE_MINUTES,
    )
    if not data or data.get("code") != 200:
        logger.warning("抖音热搜API返回异常")
        return []

    all_items = data.get("data", [])
    shortdrama_items = []  # 短剧直接相关词条（优先级高）
    drama_items = []       # 影视相关词条（优先级低）

    for item in all_items:
        word = item.get("word", "")
        entry = {
            "position": item.get("position", 0),
            "word": word,
            "hot_value": item.get("hot_value", 0),
            "label": item.get("label", 0),
        }
        # 优先匹配短剧直接关键词（短剧、微短剧等）
        if any(kw in word for kw in SHORTDRAMA_KEYWORDS):
            shortdrama_items.append(entry)
        # 其次匹配影视/剧集相关关键词（开播、追剧、霸总等）
        elif any(kw in word for kw in DRAMA_RELATED_KEYWORDS):
            # 排除误匹配：如"剧毒"、"剧烈"、"剧增"等含"剧"但非剧集含义的词
            if not any(neg in word for neg in ["剧毒", "剧烈", "剧增", "剧集剧"]):
                drama_items.append(entry)

    return shortdrama_items + drama_items


# ============ 题材分类函数 ============
def generate_genre_stats(rank_data):
    """
    统计题材分布

    遍历所有短剧数据，对每部剧调用 classify_genre 分类，
    然后统计每种题材出现的次数。

    参数：
        rank_data: 短剧热度榜数据列表

    返回：
        字典 {"婚恋": 9, "逆袭": 5, ...}，按题材名计数
    """
    genre_count = {}
    for item in rank_data:
        title = item.get("title", "")
        genres = classify_genre(title)
        for g in genres:
            genre_count[g] = genre_count.get(g, 0) + 1
    return genre_count


# ============ 报告生成函数 ============
def generate_report(rank_data, douyin_data, genre_stats, include_analysis=True):
    """
    生成Markdown格式的结构化日报

    报告包含以下板块：
        1. 短剧热度榜 Top15（+ 可折叠的完整Top30）
        2. 抖音短剧相关热搜
        3. 题材分布统计表
        4. 选题参考（基于数据分析的建议）

    参数：
        rank_data: 短剧热度榜数据
        douyin_data: 抖音热搜筛选结果
        genre_stats: 题材分布统计
        include_analysis: 是否包含选题参考分析（默认True）

    返回：
        (report_content, date_file) 元组
    """
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

    # === 完整Top30（可折叠） ===
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
        for genre, count in sorted(genre_stats.items(), key=lambda x: -x[1]):
            pct = f"{count/total*100:.1f}%"
            lines.append(f"| {genre} | {count} | {pct} |")
        lines.append("")

    # === 选题参考 ===
    if include_analysis and rank_data:
        lines.append("## 💡 选题参考\n")
        top_genre = max(genre_stats.items(), key=lambda x: x[1]) if genre_stats else ("未知", 0)
        top3_titles = [item.get("title", "") for item in rank_data[:3]]

        lines.append(f"基于今日热度数据分析：\n")
        lines.append(f"1. **最热题材**: {top_genre[0]}类短剧（{top_genre[1]}部上榜），建议优先关注")
        lines.append(f"2. **头部剧目**: {'、'.join(top3_titles)} 持续领跑，可做对标分析")

        cold_genres = [g for g, c in genre_stats.items() if c == 1 and g != "其他"]
        if cold_genres:
            lines.append(f"3. **差异化机会**: {'、'.join(cold_genres)} 题材竞品少，可考虑切入")

        lines.append(f"4. **抖音热搜联动**: 抖音当前有 {len(douyin_data)} 条短剧相关热搜，可结合热搜做选题")
        lines.append("")

    return "\n".join(lines), date_file


def save_report(content, date_file, output_dir=None):
    """
    保存报告到本地文件

    参数：
        content: Markdown报告内容
        date_file: 日期字符串（如 "2026-05-22"）
        output_dir: 输出目录路径，None则使用config中的默认目录

    返回：
        保存的文件绝对路径
    """
    report_dir = Path(output_dir) if output_dir else config.REPORT_DIR
    report_dir.mkdir(parents=True, exist_ok=True)

    filename = f"短剧热点日报_{date_file}.md"
    filepath = report_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return str(filepath)


# ============ 控制台输出函数 ============
def print_summary(rank_data, douyin_data, genre_stats):
    """在控制台打印数据摘要"""
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


# ============ 命令行参数解析 ============
def parse_args():
    """使用 argparse 解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="短剧热点监控 + 仿制剧本生成",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python fetch_hotspot.py                        # 控制台查看摘要
  python fetch_hotspot.py --report               # 生成Markdown日报
  python fetch_hotspot.py --output ./reports      # 指定输出目录
  python fetch_hotspot.py --script --comfyui     # 生成剧本 + ComfyUI配置
  python fetch_hotspot.py --script --genre 霸总  # 指定题材
  python fetch_hotspot.py --script --batch       # 批量生成5个
        """,
    )
    parser.add_argument("--report", action="store_true", help="生成Markdown日报文件")
    parser.add_argument("--rank-only", action="store_true", help="仅获取热度榜，跳过抖音热搜")
    parser.add_argument("--script", action="store_true", help="生成仿制剧本")
    parser.add_argument("--batch", action="store_true", help="批量生成剧本")
    parser.add_argument("--comfyui", action="store_true", help="生成ComfyUI可执行配置")
    parser.add_argument("--output", type=str, default=None, help="报告输出目录")
    parser.add_argument("--genre", type=str, default=None, help="指定剧本题材")
    parser.add_argument("--ref", type=str, default=None, help="指定参考剧目")
    parser.add_argument("--count", type=int, default=5, help="批量生成数量（默认5）")
    parser.add_argument("--log-level", type=str, default=None, help="日志级别 DEBUG/INFO/WARNING/ERROR")
    return parser.parse_args()


# ============ 主函数 ============
def main():
    """主流程入口"""
    args = parse_args()

    # 设置日志级别
    if args.log_level:
        logging.getLogger("shortdrama").setLevel(getattr(logging, args.log_level.upper(), logging.INFO))

    config.ensure_dirs()

    # 步骤1：获取短剧热度榜
    print("[1/3] 获取短剧热度榜...")
    rank_data = fetch_shortdrama_rank()
    if not rank_data:
        logger.error("未能获取短剧热度榜数据，退出")
        sys.exit(1)
    print(f"  ✓ 获取到 {len(rank_data)} 条短剧排名数据")

    # 步骤2：获取抖音热搜并筛选
    douyin_data = []
    if not args.rank_only:
        print("[2/3] 获取抖音热搜...")
        douyin_data = fetch_douyin_hot()
        print(f"  ✓ 抖音热搜中筛选出 {len(douyin_data)} 条短剧相关词条")
    else:
        print("[2/3] 跳过抖音热搜（--rank-only 模式）")

    # 步骤3：统计题材分布
    print("[3/3] 统计题材分布...")
    genre_stats = generate_genre_stats(rank_data)
    print(f"  ✓ 识别到 {len(genre_stats)} 种题材类型")

    # 打印控制台摘要
    print_summary(rank_data, douyin_data, genre_stats)

    # 生成报告
    if args.report:
        content, date_file = generate_report(rank_data, douyin_data, genre_stats, include_analysis=True)
        filepath = save_report(content, date_file, args.output)
        print(f"\n📄 报告已保存: {filepath}")
    else:
        content, date_file = generate_report(rank_data, douyin_data, genre_stats, include_analysis=True)
        result = {
            "rank_data": rank_data,
            "douyin_data": douyin_data,
            "genre_stats": genre_stats,
            "report_content": content,
            "date": date_file,
        }
        print("\n---JSON_OUTPUT---")
        print(json.dumps(result, ensure_ascii=False, indent=2))

    # 步骤4：生成仿制剧本
    if args.script or args.batch:
        scripts_dir = str(config.SCRIPTS_PKG_DIR)
        sys.path.insert(0, scripts_dir)

        try:
            from generate_script import generate_script as _gen_script, generate_batch_scripts, load_templates
        except ImportError:
            logger.error("找不到 generate_script.py，请确认文件位置")
            sys.exit(1)

        templates = load_templates()
        script_output = args.output or str(config.REPORT_DIR)
        script_output = os.path.join(os.path.dirname(script_output.rstrip("/").rstrip("\\")), "shortdrama", "scripts")

        comfyui_mode = args.comfyui  # 修复：正确传递 --comfyui 参数

        if args.batch:
            print(f"\n[4/4] 批量生成 {args.count} 个仿制剧本...")
            results = generate_batch_scripts(
                rank_data, count=args.count,
                templates=templates, output_dir=script_output
            )
            print(f"\n🎬 批量生成 {len(results)} 个剧本：")
            for title, genre, filepath in results:
                print(f"  [{genre}] 《{title}》→ {filepath}")
        else:
            print("\n[4/4] 生成仿制剧本...")
            content, filepath, title, genre = _gen_script(
                rank_data, genre=args.genre, ref_title=args.ref,
                templates=templates, output_dir=script_output,
                comfyui_mode=comfyui_mode,
            )
            print(f"\n🎬 剧本已生成：")
            print(f"  题材: {genre}")
            print(f"  剧名: 《{title}》")
            print(f"  文件: {filepath}")
            if comfyui_mode:
                wf_dir = os.path.join(script_output, "workflows")
                print(f"  ComfyUI工作流: {wf_dir}")


if __name__ == "__main__":
    main()
