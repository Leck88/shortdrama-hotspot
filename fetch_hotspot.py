#!/usr/bin/env python3
"""
短剧热点监控脚本 (Shortdrama Hotspot Monitor)

功能概述：
1. 获取短剧热度排行榜 Top30 —— 调用酷乐免费API，获取当日最新短剧热度排名
2. 获取抖音热搜并筛选短剧相关词条 —— 调用小小API获取抖音热搜，用关键词匹配筛选短剧/影视相关内容
3. 题材自动分类 —— 根据剧名关键词，将短剧归类为婚恋、霸总、甜宠、逆袭等10种题材
4. 生成结构化日报 —— 输出Markdown格式报告，包含热度榜、抖音热搜、题材分布、选题参考

使用方式：
  python fetch_hotspot.py                        # 控制台查看摘要，输出JSON
  python fetch_hotspot.py --report               # 生成Markdown日报文件
  python fetch_hotspot.py --rank-only            # 仅获取热度榜，跳过抖音热搜
  python fetch_hotspot.py --output "D:/reports"  # 指定报告输出目录

数据源说明：
  - 短剧热度榜：https://api.kuleu.com/api/shortdramarank （免费，无需Key，每日更新30条）
  - 抖音热搜：https://v2.xxapi.cn/api/douyinhot （免费，无需Key，实时更新）

依赖：无第三方依赖，仅使用 Python 3 标准库
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

# ============ 配置区域 ============

# 短剧热度榜API地址（酷乐API，免费，无需鉴权）
SHORTDRAMA_API = "https://api.kuleu.com/api/shortdramarank"

# 抖音热搜榜API地址（小小API，免费，无需鉴权）
DOUYIN_HOT_API = "https://v2.xxapi.cn/api/douyinhot"

# 报告默认保存目录
DEFAULT_REPORT_DIR = r"D:\视频生产\reports\shortdrama"

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

def fetch_json(url, timeout=15):
    """
    通用JSON API请求函数
    
    参数：
        url: API接口地址
        timeout: 请求超时时间（秒），默认15秒
    
    返回：
        解析后的JSON字典，请求失败返回None
    
    说明：
        使用 urllib 标准库发送GET请求，添加User-Agent头避免被拦截
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[ERROR] 请求 {url} 失败: {e}", file=sys.stderr)
        return None


def fetch_shortdrama_rank():
    """
    获取短剧热度排行榜
    
    调用酷乐API获取当日Top30短剧排名数据。
    每条数据包含：ranking（排名）、title（剧名）、hots（热度值，如"212.3w"）
    
    返回：
        列表，每项为字典 {"ranking": 1, "title": "剧名", "hots": "212.3w"}
        请求失败返回空列表
    """
    data = fetch_json(SHORTDRAMA_API)
    if not data or data.get("code") != 200:
        print("[WARN] 短剧热度榜API返回异常", file=sys.stderr)
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
    data = fetch_json(DOUYIN_HOT_API)
    if not data or data.get("code") != 200:
        print("[WARN] 抖音热搜API返回异常", file=sys.stderr)
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

def classify_genre(title):
    """
    根据剧名关键词自动分类题材
    
    工作原理：
        遍历 genre_map 中的题材类型和对应关键词，
        如果剧名中包含某题材的任一关键词，则归入该题材。
        一部剧可能同时属于多个题材（如"离婚后闪婚"同时属于婚恋和逆袭/翻盘）。
        未匹配任何关键词的归入"其他"。
    
    题材分类说明：
        霸总 —— 总裁/首富/豪门等权力型男主
        婚恋 —— 婚姻/恋爱/夫妻关系相关
        甜宠 —— 甜蜜/宠爱/恋爱向
        逆袭 —— 弱者翻盘/崛起/无敌
        重生 —— 重生/穿越/回到过去
        古装 —— 古代背景/宫廷/侯府
        复仇 —— 复仇/报仇/恩怨
        悬疑 —— 案件/真相/谍战
        战神 —— 战斗/修仙/武力型
        逆袭/翻盘 —— 离婚/出狱后翻盘
    
    参数：
        title: 剧名（字符串）
    
    返回：
        题材标签列表，如 ["婚恋", "逆袭/翻盘"]；无匹配返回 ["其他"]
    """
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
        report_content: Markdown文本
        date_file: 日期字符串，如 "2026-05-22"
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
            # 热度值格式化：>=1万显示为 "xx.xw"，否则直接显示
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
        # 按数量降序排列
        for genre, count in sorted(genre_stats.items(), key=lambda x: -x[1]):
            pct = f"{count/total*100:.1f}%"
            lines.append(f"| {genre} | {count} | {pct} |")
        lines.append("")
    
    # === 选题参考（数据分析建议） ===
    if include_analysis and rank_data:
        lines.append("## 💡 选题参考\n")
        
        # 找最热门题材
        top_genre = max(genre_stats.items(), key=lambda x: x[1]) if genre_stats else ("未知", 0)
        top3_titles = [item.get("title", "") for item in rank_data[:3]]
        
        lines.append(f"基于今日热度数据分析：\n")
        lines.append(f"1. **最热题材**: {top_genre[0]}类短剧（{top_genre[1]}部上榜），建议优先关注")
        lines.append(f"2. **头部剧目**: {'、'.join(top3_titles)} 持续领跑，可做对标分析")
        
        # 冷门机会：只有1部上榜的题材，竞品少，差异化空间大
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
        output_dir: 输出目录路径，None则使用默认目录
    
    返回：
        保存的文件绝对路径
    """
    report_dir = Path(output_dir) if output_dir else Path(DEFAULT_REPORT_DIR)
    # 自动创建目录（如不存在）
    report_dir.mkdir(parents=True, exist_ok=True)
    
    filename = f"短剧热点日报_{date_file}.md"
    filepath = report_dir / filename
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    
    return str(filepath)


# ============ 控制台输出函数 ============

def print_summary(rank_data, douyin_data, genre_stats):
    """
    在控制台打印数据摘要，方便快速浏览
    
    输出内容包括：
        - 短剧热度榜 Top5
        - 抖音短剧相关热搜（最多5条）
        - 题材分布（前5种）
    """
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


# ============ 主函数 ============

def main():
    """
    主流程入口
    
    执行步骤：
        1. 解析命令行参数（--report, --rank-only, --output, --script等）
        2. 获取短剧热度榜数据
        3. 获取抖音热搜数据（--rank-only模式下跳过）
        4. 统计题材分布
        5. 打印控制台摘要
        6. 根据参数生成日报文件或输出JSON
        7. 如果指定 --script，生成仿制剧本
    """
    # 解析命令行参数
    args = set(sys.argv[1:])
    rank_only = "--rank-only" in args      # 仅获取热度榜，跳过抖音热搜
    gen_report = "--report" in args        # 生成Markdown日报文件
    gen_script = "--script" in args        # 生成仿制剧本
    batch_script = "--batch" in args       # 批量生成剧本
    output_dir = None
    script_genre = None                    # 指定剧本题材
    script_ref = None                      # 指定参考剧目
    script_count = 5                       # 批量生成数量
    
    # 解析参数
    for i, arg in enumerate(sys.argv):
        if arg == "--output" and i + 1 < len(sys.argv):
            output_dir = sys.argv[i + 1]
        elif arg == "--genre" and i + 1 < len(sys.argv):
            script_genre = sys.argv[i + 1]
        elif arg == "--ref" and i + 1 < len(sys.argv):
            script_ref = sys.argv[i + 1]
        elif arg == "--count" and i + 1 < len(sys.argv):
            script_count = int(sys.argv[i + 1])
    
    # 步骤1：获取短剧热度榜
    print("[1/3] 获取短剧热度榜...")
    rank_data = fetch_shortdrama_rank()
    if not rank_data:
        print("[ERROR] 未能获取短剧热度榜数据，退出", file=sys.stderr)
        sys.exit(1)
    print(f"  ✓ 获取到 {len(rank_data)} 条短剧排名数据")
    
    # 步骤2：获取抖音热搜并筛选
    douyin_data = []
    if not rank_only:
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
    if gen_report:
        # --report 模式：生成Markdown日报文件
        content, date_file = generate_report(rank_data, douyin_data, genre_stats, include_analysis=True)
        filepath = save_report(content, date_file, output_dir)
        print(f"\n📄 报告已保存: {filepath}")
    else:
        # 默认模式：生成报告内容并通过JSON输出，供其他程序/WorkBuddy skill解析
        content, date_file = generate_report(rank_data, douyin_data, genre_stats, include_analysis=True)
        result = {
            "rank_data": rank_data,          # 短剧热度榜原始数据
            "douyin_data": douyin_data,      # 抖音热搜筛选结果
            "genre_stats": genre_stats,      # 题材分布统计
            "report_content": content,       # Markdown报告全文
            "date": date_file,               # 日期字符串
        }
        print("\n---JSON_OUTPUT---")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    
    # 步骤4：生成仿制剧本（如果指定了 --script 或 --batch）
    if gen_script or batch_script:
        # 动态导入剧本生成模块
        script_dir = os.path.dirname(os.path.abspath(__file__))
        scripts_dir = os.path.join(script_dir, "scripts") if os.path.exists(os.path.join(script_dir, "scripts")) else script_dir
        sys.path.insert(0, scripts_dir)
        
        try:
            from generate_script import generate_script as _gen_script, generate_batch_scripts, load_templates
        except ImportError:
            # 尝试从同级目录导入
            gen_module_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generate_script.py")
            if not os.path.exists(gen_module_path):
                gen_module_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "generate_script.py")
            print(f"[ERROR] 找不到 generate_script.py，请确认文件位置", file=sys.stderr)
            sys.exit(1)
        
        templates = load_templates()
        script_output = output_dir or DEFAULT_REPORT_DIR
        # 剧本保存到 scripts 子目录
        script_output = os.path.join(os.path.dirname(script_output.rstrip("/").rstrip("\\")), "shortdrama", "scripts")
        
        if batch_script:
            print(f"\n[4/4] 批量生成 {script_count} 个仿制剧本...")
            results = generate_batch_scripts(
                rank_data, count=script_count,
                templates=templates, output_dir=script_output
            )
            print(f"\n🎬 批量生成 {len(results)} 个剧本：")
            for title, genre, filepath in results:
                print(f"  [{genre}] 《{title}》→ {filepath}")
        else:
            print("\n[4/4] 生成仿制剧本...")
            content, filepath, title, genre = _gen_script(
                rank_data, genre=script_genre, ref_title=script_ref,
                templates=templates, output_dir=script_output
            )
            print(f"\n🎬 剧本已生成：")
            print(f"  题材: {genre}")
            print(f"  剧名: 《{title}》")
            print(f"  文件: {filepath}")


if __name__ == "__main__":
    main()
