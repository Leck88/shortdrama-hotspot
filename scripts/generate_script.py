#!/usr/bin/env python3
"""
短剧仿制剧本生成脚本 (Shortdrama Script Generator)

功能概述：
1. 爆款拆解 —— 分析热门短剧的共性要素（钩子、命名模式、冲突类型）
2. 仿制剧本生成 —— 基于爆款拆解 + 题材模板，生成完整的2分钟短剧剧本
3. 批量模式 —— 基于当日Top5热门题材，批量生成仿制剧本

使用方式：
  python generate_script.py --rank-data <json_file> --script       # 基于最热题材生成1个剧本
  python generate_script.py --rank-data <json_file> --script --genre "霸总"  # 指定题材
  python generate_script.py --rank-data <json_file> --script --ref "XX"      # 参考特定剧目
  python generate_script.py --rank-data <json_file> --script --batch         # 批量生成5个

依赖：无第三方依赖，仅使用 Python 3 标准库
"""

import json
import os
import random
import sys
from datetime import datetime
from pathlib import Path

# ============ 配置 ============

# 模板文件路径
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
GENRE_TEMPLATE_FILE = os.path.join(TEMPLATE_DIR, "genre_templates.json")

# 剧本默认输出目录
DEFAULT_SCRIPT_DIR = r"D:\视频生产\reports\shortdrama\scripts"

# 爆款命名模式元素
NAMING_ELEMENTS = {
    "事件": ["离婚", "出狱", "破产", "重生", "穿越", "闪婚", "退婚", "继承", "归来", "摊牌"],
    "身份": ["总裁", "首富", "战神", "千金", "太子", "王爷", "侯爷", "大佬", "高手", "暗帝"],
    "情感": ["宠爱", "沦陷", "上瘾", "心动", "跪求", "团宠", "独宠", "偏执", "强迫"],
    "反转": ["竟是", "原来是", "没想到", "居然是", "不料", "竟成了"],
    "结果": ["走上巅峰", "全家慌了", "跪地求", "震惊全场", "无敌天下", "震朝堂"],
}


def load_templates():
    """
    加载题材模板
    
    从 genre_templates.json 读取10种题材的剧本结构模板。
    
    返回：
        字典，键为题材名，值为模板内容
    """
    with open(GENRE_TEMPLATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def classify_genre(title):
    """
    根据剧名分类题材（与 fetch_hotspot.py 保持一致）
    
    参数：
        title: 剧名
    
    返回：
        题材标签列表
    """
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


# ============ 爆款拆解 ============

def analyze_hit_pattern(rank_data, top_n=5):
    """
    拆解爆款短剧的共性要素
    
    分析 Top N 热门短剧，提取：
    - 热门题材分布
    - 钩子元素（剧名中的冲突/反转/身份关键词）
    - 爆款命名模式
    
    参数：
        rank_data: 短剧热度榜数据列表
        top_n: 分析前N部剧，默认5
    
    返回：
        字典，包含 genres（题材分布）、hooks（钩子元素）、patterns（命名模式）
    """
    top_items = rank_data[:top_n]
    
    # 统计题材分布
    genre_count = {}
    for item in top_items:
        title = item.get("title", "")
        genres = classify_genre(title)
        for g in genres:
            genre_count[g] = genre_count.get(g, 0) + 1
    
    # 提取钩子元素
    hook_keywords = {
        "冲突型": ["离婚", "出狱", "退婚", "撤资", "被赶出"],
        "身份型": ["总裁", "首富", "千金", "战神", "太子"],
        "反转型": ["竟是", "原来", "没想到", "居然"],
        "情感型": ["宠", "爱", "恋", "宠妻", "上瘾"],
        "权力型": ["巅峰", "无敌", "震", "最强"],
    }
    
    found_hooks = {}
    for item in top_items:
        title = item.get("title", "")
        for hook_type, keywords in hook_keywords.items():
            for kw in keywords:
                if kw in title:
                    if hook_type not in found_hooks:
                        found_hooks[hook_type] = []
                    if kw not in found_hooks[hook_type]:
                        found_hooks[hook_type].append(kw)
    
    # 归纳命名模式
    patterns = []
    for item in top_items:
        title = item.get("title", "")
        if "，" in title:
            parts = title.split("，")
            patterns.append({"结构": "转折型", "前半": parts[0], "后半": parts[1] if len(parts) > 1 else ""})
        elif "的" in title:
            patterns.append({"结构": "所属型", "模板": "XX的XX"})
        else:
            patterns.append({"结构": "直白型", "模板": title[:4] + "..."})
    
    return {
        "top_genres": sorted(genre_count.items(), key=lambda x: -x[1]),
        "hooks": found_hooks,
        "patterns": patterns[:top_n],
        "top_titles": [item.get("title", "") for item in top_items],
    }


# ============ 剧名/梗概生成 ============

def generate_title(genre, templates, hit_analysis=None):
    """
    基于题材模板和爆款分析，生成仿制剧名
    
    参数：
        genre: 目标题材
        templates: 题材模板字典
        hit_analysis: 爆款拆解结果（可选）
    
    返回：
        生成的剧名字符串
    """
    template = templates.get(genre, templates.get("婚恋", {}))
    naming_patterns = template.get("naming_patterns", ["XX的XX"])
    
    # 随机选一个命名模式
    pattern = random.choice(naming_patterns)
    
    # 基于命名模式填充元素
    if "XX后，XX了" in pattern or "XX后，" in pattern:
        event = random.choice(NAMING_ELEMENTS["事件"])
        result = random.choice(NAMING_ELEMENTS["结果"])
        return f"{event}后，{result}"
    elif "闪婚" in pattern or "离婚" in pattern or "领证" in pattern:
        event = random.choice(["闪婚", "离婚", "领证"])
        identity = random.choice(NAMING_ELEMENTS["身份"])
        emotion = random.choice(NAMING_ELEMENTS["情感"])
        return f"{event}{identity}，{emotion}日常"
    elif "竟是" in pattern or "原来" in pattern:
        identity1 = random.choice(NAMING_ELEMENTS["身份"])
        identity2 = random.choice(NAMING_ELEMENTS["身份"])
        while identity1 == identity2:
            identity2 = random.choice(NAMING_ELEMENTS["身份"])
        return f"{identity1}竟是{identity2}"
    elif "人前" in pattern:
        identity = random.choice(NAMING_ELEMENTS["身份"])
        event = random.choice(NAMING_ELEMENTS["事件"])
        return f"人前不熟，人后{random.choice(NAMING_ELEMENTS['情感'])}"
    elif "只对她" in pattern:
        identity = random.choice(NAMING_ELEMENTS["身份"])
        emotion = random.choice(NAMING_ELEMENTS["情感"])
        return f"只对她{emotion}"
    else:
        event = random.choice(NAMING_ELEMENTS["事件"])
        result = random.choice(NAMING_ELEMENTS["结果"])
        return f"{event}，{result}"


def generate_synopsis(genre, templates, title, ref_title=None):
    """
    基于题材模板生成一句话梗概
    
    参数：
        genre: 题材
        templates: 题材模板
        title: 生成的剧名
        ref_title: 参考剧目名（可选）
    
    返回：
        一句话梗概字符串
    """
    template = templates.get(genre, templates.get("婚恋", {}))
    conflicts = template.get("conflicts", [])
    reversals = template.get("reversals", [])
    
    conflict = random.choice(conflicts) if conflicts else "遭遇不公"
    reversal = random.choice(reversals) if reversals else "真相大白"
    
    ref_note = f"（灵感源自《{ref_title}》）" if ref_title else ""
    
    return f"女主{conflict}，在绝境中隐忍蓄力，最终{reversal}，实现华丽逆袭{ref_note}"


# ============ 分场剧本生成 ============

def generate_scenes(genre, templates):
    """
    基于题材模板生成分场剧本
    
    参数：
        genre: 题材
        templates: 题材模板
    
    返回：
        分场剧本列表
    """
    template = templates.get(genre, templates.get("婚恋", {}))
    structure = template.get("structure", {})
    characters = template.get("characters", {})
    conflicts = template.get("conflicts", [])
    reversals = template.get("reversals", [])
    hooks = template.get("hooks", {})
    
    # 角色名称池
    female_names = ["苏晚", "林念", "沈清", "顾念", "叶棠", "温如言", "江璃", "白鹿"]
    male_names = ["陆衍", "顾深", "傅修", "沈墨", "萧凛", "霍渊", "裴峥", "封诀"]
    
    female_name = random.choice(female_names)
    male_name = random.choice(male_names)
    
    # 角色设定
    char_settings = {}
    for role, desc in characters.items():
        if "女主" in role:
            char_settings[role] = f"{female_name}（{desc}）"
        elif "男主" in role:
            char_settings[role] = f"{male_name}（{desc}）"
        else:
            char_settings[role] = desc
    
    # 分场
    scenes = []
    scene_templates = [
        {
            "name": "开场钩子",
            "duration": "0-3秒",
            "structure_key": "钩子开场",
            "template": "画面：{hook_visual}\n旁白/字幕：{hook_line}\n💥 爆点：用3秒抓住观众——{hook_point}",
        },
        {
            "name": "矛盾建立",
            "duration": "3-30秒",
            "structure_key": "矛盾建立",
            "template": "场景：{conflict_scene}\n{female_name}（{conflict_emotion}）：{conflict_line}\n{male_name}（冷淡/无奈）：{response_line}\n💥 爆点：{conflict_point}",
        },
        {
            "name": "冲突升级",
            "duration": "30-90秒",
            "structure_key": "冲突升级",
            "template": "场景：{escalate_scene}\n{villain}（嚣张）：{villain_line}\n{female_name}（隐忍中爆发）：{hero_line}\n💥 爆点：{escalate_point}",
        },
        {
            "name": "高潮反转",
            "duration": "90-135秒",
            "structure_key": "高潮反转",
            "template": "场景：{climax_scene}\n{male_name}（当众宣布/揭露）：{reveal_line}\n全场震惊！\n{female_name}（泪目/震撼）：{reaction_line}\n💥 爆点：{climax_point}",
        },
        {
            "name": "钩子结尾",
            "duration": "135-150秒",
            "structure_key": "钩子结尾",
            "template": "场景：{ending_scene}\n画面：{ending_visual}\n字幕/旁白：{ending_line}\n💥 爆点：{ending_point}",
        },
    ]
    
    conflict = random.choice(conflicts) if conflicts else "遭遇不公"
    reversal = random.choice(reversals) if reversals else "真相大白"
    opening_hooks = hooks.get("开场钩子", ["震撼场面"])
    ending_hooks = hooks.get("结尾悬念", ["新悬念"])
    
    for scene_tpl in scene_templates:
        scene = {
            "name": scene_tpl["name"],
            "duration": scene_tpl["duration"],
            "structure_desc": structure.get(scene_tpl["structure_key"], ""),
        }
        scenes.append(scene)
    
    return {
        "scenes": scenes,
        "characters": char_settings,
        "female_name": female_name,
        "male_name": male_name,
        "conflict": conflict,
        "reversal": reversal,
        "opening_hook": random.choice(opening_hooks) if opening_hooks else "震撼开场",
        "ending_hook": random.choice(ending_hooks) if ending_hooks else "留悬念",
    }


def render_script_md(title, genre, ref_title, templates, scene_data, rank_info=""):
    """
    将剧本数据渲染为Markdown格式
    
    参数：
        title: 剧名
        genre: 题材
        ref_title: 参考剧目
        templates: 题材模板
        scene_data: 分场数据
        rank_info: 热度排名信息
    
    返回：
        Markdown格式的完整剧本
    """
    now = datetime.now()
    lines = []
    
    lines.append(f"# 《{title}》- 短剧剧本\n")
    lines.append(f"> 生成时间: {now.strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # 基本信息
    lines.append("## 基本信息\n")
    lines.append(f"- **剧名**: 《{title}》")
    lines.append(f"- **题材**: {genre}")
    lines.append(f"- **时长**: 约2分钟（150秒）")
    if ref_title:
        lines.append(f"- **参考剧目**: 《{ref_title}》")
    if rank_info:
        lines.append(f"- **仿制依据**: {rank_info}")
    lines.append("")
    
    # 一句话梗概
    synopsis = generate_synopsis(genre, templates, title, ref_title)
    lines.append("## 一句话梗概\n")
    lines.append(f"{synopsis}\n")
    
    # 人物设定
    lines.append("## 人物设定\n")
    lines.append("| 角色 | 设定 |")
    lines.append("|------|------|")
    for role, desc in scene_data["characters"].items():
        lines.append(f"| {role} | {desc} |")
    lines.append("")
    
    # 核心冲突与反转
    lines.append("## 核心冲突与反转\n")
    lines.append(f"- **核心冲突**: {scene_data['conflict']}")
    lines.append(f"- **关键反转**: {scene_data['reversal']}")
    lines.append("")
    
    # 分场剧本
    lines.append("## 分场剧本\n")
    
    fn = scene_data["female_name"]
    mn = scene_data["male_name"]
    
    for i, scene in enumerate(scene_data["scenes"], 1):
        lines.append(f"### 第{i}场：{scene['name']}（{scene['duration']}）\n")
        lines.append(f"**结构要求**: {scene['structure_desc']}\n")
        
        # 根据场景类型生成具体内容
        if i == 1:  # 开场钩子
            lines.append(f"- **画面**: {scene_data['opening_hook']}")
            lines.append(f"- **旁白/字幕**: 「这一天，{fn}的人生彻底改变了——」")
            lines.append(f"- 💥 **爆点**: 3秒内建立核心悬念，让观众停不下来")
        elif i == 2:  # 矛盾建立
            lines.append(f"- **场景**: {fn}面对{scene_data['conflict']}的处境")
            lines.append(f"- **{fn}**（倔强）:「我不会认输的。」")
            lines.append(f"- **{mn}**（冷淡/复杂）:「你还有别的选择吗？」")
            lines.append(f"- 💥 **爆点**: 矛盾建立的同时埋下伏笔，暗示{mn}的态度不简单")
        elif i == 3:  # 冲突升级
            lines.append(f"- **场景**: 冲突升级——{scene_data['conflict']}愈演愈烈")
            lines.append(f"- **反派**（嚣张）:「你以为你是谁？」")
            lines.append(f"- **{fn}**（隐忍→爆发）:「你等着。」")
            lines.append(f"- **{mn}**（暗处观察，表情复杂）")
            lines.append(f"- 💥 **爆点**: 主角被逼到绝境，观众愤怒值拉满，期待反转")
        elif i == 4:  # 高潮反转
            lines.append(f"- **场景**: {scene_data['reversal']}")
            lines.append(f"- **{mn}**（当众）:「她是我的人/我真实的身份是——」")
            lines.append(f"- 全场震惊")
            lines.append(f"- **{fn}**（震撼/泪目）:「你……一直都知道？」")
            lines.append(f"- 💥 **爆点**: 全剧最强反转，之前所有伏笔回收，观众爽感爆发")
        elif i == 5:  # 钩子结尾
            lines.append(f"- **画面**: {scene_data['ending_hook']}")
            lines.append(f"- **旁白/字幕**: 「一切，才刚刚开始……」")
            lines.append(f"- 💥 **爆点**: 留下强悬念，让观众追下一集")
        
        lines.append("")
    
    # 钩子设计
    lines.append("## 钩子设计\n")
    lines.append(f"- **开头钩子**: {scene_data['opening_hook']}（3秒内抓住观众）")
    lines.append(f"- **结尾悬念**: {scene_data['ending_hook']}（引导追更下一集）")
    lines.append("")
    
    # 拍摄提示
    lines.append("## 拍摄提示\n")
    lines.append("- 本剧本适配竖屏短剧格式（9:16）")
    lines.append("- 建议每场1-2个机位，快节奏切换")
    lines.append("- 对白精简，每句不超过15字")
    lines.append("- 情绪转折点配合音乐切换")
    lines.append("- 开头3秒和结尾12秒为关键留存点，务必精彩")
    lines.append("")
    
    return "\n".join(lines)


# ============ 主生成函数 ============

def generate_script(rank_data, genre=None, ref_title=None, templates=None, output_dir=None):
    """
    生成仿制剧本
    
    参数：
        rank_data: 热度榜数据
        genre: 目标题材（None则自动选择最热题材）
        ref_title: 参考剧目（None则自动选择Top1）
        templates: 题材模板（None则自动加载）
        output_dir: 输出目录
    
    返回：
        (script_content, filepath) 元组
    """
    if not templates:
        templates = load_templates()
    
    # 爆款拆解
    hit_analysis = analyze_hit_pattern(rank_data)
    
    # 确定题材
    if not genre:
        if hit_analysis["top_genres"]:
            genre = hit_analysis["top_genres"][0][0]
        else:
            genre = "婚恋"
    
    # 确保题材在模板中
    if genre not in templates:
        genre = "婚恋"  # 回退到默认题材
    
    # 确定参考剧目
    if not ref_title:
        if hit_analysis["top_titles"]:
            ref_title = hit_analysis["top_titles"][0]
        else:
            ref_title = "热门短剧"
    
    # 找到参考剧目的排名信息
    rank_info = ""
    for item in rank_data:
        if item.get("title") == ref_title:
            rank_info = f"当日热度#{item.get('ranking', '?')}，热度{item.get('hots', '?')}"
            break
    
    # 生成剧名
    title = generate_title(genre, templates, hit_analysis)
    
    # 生成分场数据
    scene_data = generate_scenes(genre, templates)
    
    # 渲染Markdown剧本
    content = render_script_md(title, genre, ref_title, templates, scene_data, rank_info)
    
    # 保存
    now = datetime.now()
    date_file = now.strftime("%Y-%m-%d")
    
    script_dir = Path(output_dir) if output_dir else Path(DEFAULT_SCRIPT_DIR)
    script_dir.mkdir(parents=True, exist_ok=True)
    
    # 文件名：题材_剧名_日期.md（清理文件名中的非法字符）
    safe_title = title[:10].replace("，", "").replace("、", "").replace(" ", "").replace("/", "").replace("\\", "").replace(":", "")
    safe_genre = genre.replace("/", "").replace("\\", "").replace(":", "")
    filename = f"{safe_genre}_{safe_title}_{date_file}.md"
    filepath = script_dir / filename
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    
    return content, str(filepath), title, genre


def generate_batch_scripts(rank_data, count=5, templates=None, output_dir=None):
    """
    批量生成仿制剧本
    
    基于当日热度榜Top5热门题材，每种题材生成1个剧本。
    
    参数：
        rank_data: 热度榜数据
        count: 生成数量（默认5）
        templates: 题材模板
        output_dir: 输出目录
    
    返回：
        列表，每项为 (title, genre, filepath) 元组
    """
    if not templates:
        templates = load_templates()
    
    hit_analysis = analyze_hit_pattern(rank_data, top_n=count)
    
    results = []
    generated_genres = set()
    
    # 优先按热门题材生成
    for genre, _ in hit_analysis["top_genres"]:
        if len(results) >= count:
            break
        if genre in generated_genres or genre == "其他":
            continue
        if genre not in templates:
            continue
        
        generated_genres.add(genre)
        
        # 找该题材下的参考剧目
        ref_title = None
        for item in rank_data:
            title = item.get("title", "")
            genres = classify_genre(title)
            if genre in genres:
                ref_title = title
                break
        
        content, filepath, script_title, g = generate_script(
            rank_data, genre=genre, ref_title=ref_title,
            templates=templates, output_dir=output_dir
        )
        results.append((script_title, genre, filepath))
    
    # 如果热门题材不够，用其他题材补
    all_genres = list(templates.keys())
    for genre in all_genres:
        if len(results) >= count:
            break
        if genre in generated_genres:
            continue
        
        generated_genres.add(genre)
        ref_title = hit_analysis["top_titles"][0] if hit_analysis["top_titles"] else None
        
        content, filepath, script_title, g = generate_script(
            rank_data, genre=genre, ref_title=ref_title,
            templates=templates, output_dir=output_dir
        )
        results.append((script_title, genre, filepath))
    
    return results


# ============ 独立运行入口 ============

def main():
    """独立运行时的入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="短剧仿制剧本生成")
    parser.add_argument("--rank-data", required=True, help="热度榜JSON文件路径")
    parser.add_argument("--script", action="store_true", help="生成仿制剧本")
    parser.add_argument("--genre", help="指定剧本题材")
    parser.add_argument("--ref", help="指定参考剧目")
    parser.add_argument("--batch", action="store_true", help="批量生成")
    parser.add_argument("--count", type=int, default=5, help="批量生成数量")
    parser.add_argument("--output", help="输出目录")
    
    args = parser.parse_args()
    
    # 加载热度榜数据
    with open(args.rank_data, "r", encoding="utf-8") as f:
        rank_data = json.load(f)
    
    templates = load_templates()
    
    if args.batch:
        results = generate_batch_scripts(
            rank_data, count=args.count,
            templates=templates, output_dir=args.output
        )
        print(f"\n✅ 批量生成 {len(results)} 个剧本：")
        for title, genre, filepath in results:
            print(f"  [{genre}] 《{title}》→ {filepath}")
    elif args.script:
        content, filepath, title, genre = generate_script(
            rank_data, genre=args.genre, ref_title=args.ref,
            templates=templates, output_dir=args.output
        )
        print(f"\n✅ 剧本已生成：")
        print(f"  题材: {genre}")
        print(f"  剧名: 《{title}》")
        print(f"  文件: {filepath}")
    else:
        print("请指定 --script 或 --batch 参数")


if __name__ == "__main__":
    main()
