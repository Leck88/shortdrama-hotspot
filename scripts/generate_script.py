#!/usr/bin/env python3
"""
短剧仿制剧本生成脚本 v2.0 (Shortdrama Script Generator)

功能概述：
1. 爆款拆解 —— 分析热门短剧的共性要素（钩子、命名模式、冲突类型）
2. 仿制剧本生成 —— 基于爆款拆解 + 题材模板，生成完整的2分钟短剧剧本
3. ComfyUI可执行配置 —— 每场输出SDXL提示词 + Wan2.2运动提示词 + 工作流参数
4. 批量模式 —— 基于当日Top5热门题材，批量生成仿制剧本

使用方式：
  python generate_script.py --rank-data <json> --script              # 基于最热题材生成1个剧本
  python generate_script.py --rank-data <json> --script --genre "霸总"  # 指定题材
  python generate_script.py --rank-data <json> --script --batch       # 批量生成5个
  python generate_script.py --rank-data <json> --script --comfyui     # 生成ComfyUI可执行配置

输出说明：
  - 默认输出Markdown剧本（含ComfyUI提示词和配置）
  - --comfyui模式下额外输出各场的workflow JSON（可直接导入ComfyUI执行）
  - 所有分镜默认1080x1920竖屏分辨率

依赖：无第三方依赖，仅使用 Python 3 标准库
"""

import json
import logging
import os
import random
import sys
from datetime import datetime
from pathlib import Path

# 项目内部模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from utils.genre import classify_genre as _shared_classify_genre

# ============ 配置 ============

# 模板文件路径
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
GENRE_TEMPLATE_FILE = os.path.join(TEMPLATE_DIR, "genre_templates.json")
COMFYUI_CONFIG_FILE = os.path.join(TEMPLATE_DIR, "comfyui_pipeline_config.json")

# 工作流文件路径
WORKFLOW_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "workflows")

# 剧本默认输出目录
DEFAULT_SCRIPT_DIR = r"D:\视频生产\reports\shortdrama\scripts"

# ============ 1080P竖屏短剧 ComfyUI 提示词模板 ============

# 每种题材对应的SDXL正向提示词模板（英文，ComfyUI需要）
GENRE_SDXL_PROMPTS = {
    "婚恋": {
        "scene_style": "cinematic lighting, dramatic composition, portrait photography, 9:16 vertical frame, modern urban setting",
        "characters": "beautiful chinese woman elegant dress, handsome man in business suit, emotional expression",
        "mood": "romantic drama, tense atmosphere, high quality, masterpiece, 4k, photorealistic",
        "motion_templates": [
            "woman slapping document on table, angry expression, camera zoom in",
            "man standing in doorway, backlit silhouette, dramatic lighting",
            "couple in wedding venue, people turning around shocked, slow motion",
            "woman crying in rain, cinematic close-up, tears streaming",
            "hand holding wedding ring, soft bokeh background, shallow depth of field"
        ]
    },
    "霸总": {
        "scene_style": "luxury interior, CEO office, penthouse, cinematic lighting, 9:16 vertical frame",
        "characters": "dominant handsome man in expensive suit, confident woman standing her ground",
        "mood": "power dynamic, tension, authority, high quality, masterpiece, 4k, photorealistic",
        "motion_templates": [
            "man throwing contract on desk, dominant pose, camera low angle",
            "woman standing up defiantly, chin raised, medium shot",
            "man grabbing woman's wrist, intense eye contact, close-up",
            "luxury car door opening, man stepping out, slow motion entrance",
            "boardroom scene, everyone standing, man at head of table"
        ]
    },
    "甜宠": {
        "scene_style": "warm soft lighting, pastel colors, cozy interior, 9:16 vertical frame",
        "characters": "cute young woman casual clothes, tall handsome man gentle smile",
        "mood": "sweet romantic, heartwarming, soft focus, high quality, masterpiece, 4k",
        "motion_templates": [
            "man wall-pinning woman, gentle smile, heartbeat reaction, close-up",
            "couple sharing umbrella, laughing together, soft rain, slow motion",
            "man wrapping coat around woman, tender gesture, medium shot",
            "accidental fall, catching each other, eye contact moment",
            "feeding each other food, playful banter, warm lighting"
        ]
    },
    "逆袭": {
        "scene_style": "dramatic contrast lighting, from dark to bright, 9:16 vertical frame",
        "characters": "determined person in humble clothes transforming to powerful figure",
        "mood": "underdog story, satisfying reveal, high quality, masterpiece, 4k, photorealistic",
        "motion_templates": [
            "person kneeling on ground, rain pouring, then standing up slowly",
            "ripping off disguise revealing expensive clothes underneath, slow motion",
            "walking into room, everyone bowing, camera following from behind",
            "slamming hand on table, everyone shocked, dramatic zoom",
            "former bullies kneeling and begging, crowd watching in awe"
        ]
    },
    "重生": {
        "scene_style": "ethereal lighting, time transition effect, 9:16 vertical frame",
        "characters": "person with knowing expression, determined eyes, dual timeline appearance",
        "mood": "mystical rebirth, second chance, high quality, masterpiece, 4k, photorealistic",
        "motion_templates": [
            "person opening eyes suddenly, gasping, clock spinning backwards",
            "reaching out to stop someone, deja vu moment, slow motion",
            "walking confidently knowing what happens next, smirk",
            "old calendar dissolving into new one, time transition effect",
            "standing at crossroads, choosing different path this time"
        ]
    },
    "古装": {
        "scene_style": "chinese ancient palace, traditional architecture, silk robes, 9:16 vertical frame",
        "characters": "elegant woman in hanfu, noble man in formal ancient chinese attire",
        "mood": "court intrigue, period drama, high quality, masterpiece, 4k, photorealistic",
        "motion_templates": [
            "woman in elaborate hanfu walking through palace corridor, lantern light",
            "emperor decree reading in throne room, officials kneeling",
            "tea ceremony, poisoned cup revealed, dramatic close-up",
            "sword fight in courtyard, flowing robes, slow motion",
            "woman removing hairpin, revealing true identity, gasps from court"
        ]
    },
    "复仇": {
        "scene_style": "dark moody lighting, shadows, dramatic contrast, 9:16 vertical frame",
        "characters": "cold determined person with hidden pain, antagonist looking fearful",
        "mood": "vengeance, dark justice, high quality, masterpiece, 4k, photorealistic",
        "motion_templates": [
            "person walking through rain, removing hood, face revealed slowly",
            "burning photograph, flames reflecting in cold eyes, close-up",
            "confrontation in dark warehouse, dramatic standoff",
            "revenge smile forming slowly, camera push in on eyes",
            "villain falling to knees, begging, wide shot of victory"
        ]
    },
    "悬疑": {
        "scene_style": "noir lighting, shadows, rain, neon reflections, 9:16 vertical frame",
        "characters": "detective with intense gaze, mysterious figures in shadows",
        "mood": "suspense, mystery, unsettling, high quality, masterpiece, 4k, photorealistic",
        "motion_templates": [
            "flashlight beam revealing clue in dark room, jump scare",
            "security footage playing, figure appearing behind character",
            "opening locked drawer, finding unexpected evidence, close-up hands",
            "mirror reflection showing someone behind, slow turn around",
            "evidence board with red strings, camera pulling back to reveal pattern"
        ]
    },
    "战神": {
        "scene_style": "epic battlefield, martial arts, energy effects, 9:16 vertical frame",
        "characters": "powerful warrior with battle scars, enemies cowering",
        "mood": "epic combat, overwhelming power, high quality, masterpiece, 4k, photorealistic",
        "motion_templates": [
            "warrior standing up, energy aura forming, ground cracking",
            "one punch sending enemy flying, shockwave effect, slow motion",
            "sword unsheathing, blade gleaming, enemies stepping back",
            "transformation sequence, clothes and aura changing, epic reveal",
            "standing atop mountain of defeated enemies, wind blowing, wide shot"
        ]
    },
    "逆袭/翻盘": {
        "scene_style": "transitional lighting from dark to golden, 9:16 vertical frame",
        "characters": "person going from ragged to resplendent, former oppressors in shock",
        "mood": "satisfying comeback, redemption, high quality, masterpiece, 4k, photorealistic",
        "motion_templates": [
            "signing divorce papers with steady hand, then walking out confidently",
            "prison gates opening, stepping into sunlight, determined expression",
            "walking into company as new owner, former boss's jaw dropping",
            "revealing bank account balance on phone, everyone's eyes widening",
            "from street food to luxury dining, montage transition"
        ]
    }
}

# SDXL通用反向提示词
SDXL_NEGATIVE_PROMPT = (
    "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, "
    "fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, "
    "signature, watermark, blurry, deformed, ugly, duplicate, morbid, mutilated, "
    "out of frame, extra limbs, cloned face, disfigured, gross proportions, "
    "malformed limbs, missing arms, missing legs, extra arms, extra legs, "
    "mutated hands, fused fingers, too many fingers, long neck, horizontal frame, "
    "landscape orientation"
)

# Wan2.2视频反向提示词
WAN22_NEGATIVE_PROMPT = (
    "low quality, blurry, distorted, deformed, ugly, bad anatomy, "
    "static, no motion, jitter, flicker, horizontal frame, landscape"
)

# 爆款命名模式元素
NAMING_ELEMENTS = {
    "事件": ["离婚", "出狱", "破产", "重生", "穿越", "闪婚", "退婚", "继承", "归来", "摊牌"],
    "身份": ["总裁", "首富", "战神", "千金", "太子", "王爷", "侯爷", "大佬", "高手", "暗帝"],
    "情感": ["宠爱", "沦陷", "上瘾", "心动", "跪求", "团宠", "独宠", "偏执", "强迫"],
    "反转": ["竟是", "原来是", "没想到", "居然是", "不料", "竟成了"],
    "结果": ["走上巅峰", "全家慌了", "跪地求", "震惊全场", "无敌天下", "震朝堂"],
}


def load_templates():
    """加载题材模板"""
    with open(GENRE_TEMPLATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_comfyui_config():
    """加载ComfyUI pipeline配置"""
    with open(COMFYUI_CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def classify_genre(title):
    """根据剧名分类题材（委托给共享模块 utils.genre）"""
    return _shared_classify_genre(title)


# ============ 爆款拆解 ============

def analyze_hit_pattern(rank_data, top_n=5):
    """拆解爆款短剧的共性要素"""
    top_items = rank_data[:top_n]
    
    genre_count = {}
    for item in top_items:
        title = item.get("title", "")
        genres = classify_genre(title)
        for g in genres:
            genre_count[g] = genre_count.get(g, 0) + 1
    
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
    """基于题材模板和爆款分析，生成仿制剧名"""
    template = templates.get(genre, templates.get("婚恋", {}))
    naming_patterns = template.get("naming_patterns", ["XX的XX"])
    pattern = random.choice(naming_patterns)
    
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
        return f"人前不熟，人后{random.choice(NAMING_ELEMENTS['情感'])}"
    elif "只对她" in pattern:
        return f"只对她{random.choice(NAMING_ELEMENTS['情感'])}"
    else:
        event = random.choice(NAMING_ELEMENTS["事件"])
        result = random.choice(NAMING_ELEMENTS["结果"])
        return f"{event}，{result}"


def generate_synopsis(genre, templates, title, ref_title=None):
    """基于题材模板生成一句话梗概"""
    template = templates.get(genre, templates.get("婚恋", {}))
    conflicts = template.get("conflicts", [])
    reversals = template.get("reversals", [])
    conflict = random.choice(conflicts) if conflicts else "遭遇不公"
    reversal = random.choice(reversals) if reversals else "真相大白"
    ref_note = f"（灵感源自《{ref_title}》）" if ref_title else ""
    return f"女主{conflict}，在绝境中隐忍蓄力，最终{reversal}，实现华丽逆袭{ref_note}"


# ============ ComfyUI提示词生成 ============

def generate_sdxl_prompt(genre, scene_index, scene_name, female_name, male_name):
    """
    为每场生成SDXL文生图提示词（英文）
    
    参数：
        genre: 题材
        scene_index: 场次编号(1-5)
        scene_name: 场次名称
        female_name: 女主名
        male_name: 男主名
    
    返回：
        完整的SDXL正向提示词字符串
    """
    genre_prompts = GENRE_SDXL_PROMPTS.get(genre, GENRE_SDXL_PROMPTS["婚恋"])
    
    # 根据场次选择不同的构图描述
    shot_descriptions = {
        1: "extreme close-up, intense emotion, dramatic opening shot, vertical composition",
        2: "medium shot, two characters facing each other, dialogue scene, vertical composition",
        3: "medium-long shot, conflict scene, multiple characters, dynamic composition, vertical",
        4: "close-up to wide shot reveal, dramatic climax, crowd reaction, vertical composition",
        5: "close-up, mysterious ending, cliffhanger expression, vertical composition",
    }
    
    shot = shot_descriptions.get(scene_index, "medium shot, vertical composition")
    
    # 组合完整提示词
    prompt = (
        f"{genre_prompts['scene_style']}, {genre_prompts['characters']}, "
        f"{genre_prompts['mood']}, {shot}, "
        f"scene {scene_index}: {scene_name}, "
        f"vertical portrait orientation, 1080x1920, 9:16 aspect ratio"
    )
    
    return prompt


def generate_wan22_motion_prompt(genre, scene_index):
    """
    为每场生成Wan2.2视频运动提示词（英文）
    
    参数：
        genre: 题材
        scene_index: 场次编号(1-5)
    
    返回：
        Wan2.2运动提示词字符串
    """
    genre_prompts = GENRE_SDXL_PROMPTS.get(genre, GENRE_SDXL_PROMPTS["婚恋"])
    motion_templates = genre_prompts["motion_templates"]
    
    # 每场选择对应的运动描述
    idx = (scene_index - 1) % len(motion_templates)
    base_motion = motion_templates[idx]
    
    # 添加通用运动增强词
    motion_enhance = "smooth camera movement, cinematic motion, 8 seconds duration"
    
    return f"{base_motion}, {motion_enhance}"


# ============ 分场剧本生成 ============

def generate_scenes(genre, templates):
    """基于题材模板生成分场剧本（含ComfyUI配置）"""
    template = templates.get(genre, templates.get("婚恋", {}))
    structure = template.get("structure", {})
    characters = template.get("characters", {})
    conflicts = template.get("conflicts", [])
    reversals = template.get("reversals", [])
    hooks = template.get("hooks", {})
    
    female_names = ["苏晚", "林念", "沈清", "顾念", "叶棠", "温如言", "江璃", "白鹿"]
    male_names = ["陆衍", "顾深", "傅修", "沈墨", "萧凛", "霍渊", "裴峥", "封诀"]
    
    female_name = random.choice(female_names)
    male_name = random.choice(male_names)
    
    char_settings = {}
    for role, desc in characters.items():
        if "女主" in role:
            char_settings[role] = f"{female_name}（{desc}）"
        elif "男主" in role:
            char_settings[role] = f"{male_name}（{desc}）"
        else:
            char_settings[role] = desc
    
    conflict = random.choice(conflicts) if conflicts else "遭遇不公"
    reversal = random.choice(reversals) if reversals else "真相大白"
    opening_hooks = hooks.get("开场钩子", ["震撼场面"])
    ending_hooks = hooks.get("结尾悬念", ["新悬念"])
    
    # 5场结构定义
    scene_templates = [
        {"name": "开场钩子", "duration": "0-3秒", "structure_key": "钩子开场",
         "sdxl_composition": "extreme close-up, dramatic reveal, shock expression",
         "video_duration_s": 3, "frames": 24},
        {"name": "矛盾建立", "duration": "3-30秒", "structure_key": "矛盾建立",
         "sdxl_composition": "medium shot, confrontation, dialogue scene",
         "video_duration_s": 27, "frames": 216},
        {"name": "冲突升级", "duration": "30-90秒", "structure_key": "冲突升级",
         "sdxl_composition": "medium-long shot, intense conflict, multiple angles",
         "video_duration_s": 60, "frames": 480},
        {"name": "高潮反转", "duration": "90-135秒", "structure_key": "高潮反转",
         "sdxl_composition": "wide reveal shot, crowd reaction, dramatic lighting",
         "video_duration_s": 45, "frames": 360},
        {"name": "钩子结尾", "duration": "135-150秒", "structure_key": "钩子结尾",
         "sdxl_composition": "close-up, mysterious expression, cliffhanger",
         "video_duration_s": 15, "frames": 120},
    ]
    
    scenes = []
    for i, scene_tpl in enumerate(scene_templates, 1):
        scene_idx = i
        sdxl_prompt = generate_sdxl_prompt(genre, scene_idx, scene_tpl["name"], female_name, male_name)
        wan22_motion = generate_wan22_motion_prompt(genre, scene_idx)
        
        scene = {
            "scene_id": scene_idx,
            "name": scene_tpl["name"],
            "duration": scene_tpl["duration"],
            "duration_seconds": scene_tpl["video_duration_s"],
            "structure_desc": structure.get(scene_tpl["structure_key"], ""),
            
            # === ComfyUI 可执行配置 ===
            "comfyui": {
                # SDXL图生图配置
                "sdxl": {
                    "prompt": sdxl_prompt,
                    "negative_prompt": SDXL_NEGATIVE_PROMPT,
                    "width": 1024,
                    "height": 1820,
                    "final_resize": {"width": 1080, "height": 1920},
                    "cfg_scale": 7.0,
                    "steps": 30,
                    "sampler": "euler_ancestral",
                    "scheduler": "normal",
                    "checkpoint": "sd_xl_base_1.0.safetensors",
                },
                # Wan2.2 图生视频配置
                "wan22_i2v": {
                    "motion_prompt": wan22_motion,
                    "negative_prompt": WAN22_NEGATIVE_PROMPT,
                    "input_resolution": "832x480",
                    "output_target": "1080x1920",
                    "frames": 64,
                    "fps": 8,
                    "video_duration": "8秒",
                    "cfg_scale": 7.0,
                    "steps": 30,
                    "sampler": "uni_pc_bh2",
                    "motion_strength": 0.8,
                    "model": "Wan2.1-I2V-14B-480P.safetensors",
                },
                # 时间和成本估算（4080S 32G, 1.8元/小时）
                "time_cost": {
                    "sdxl_time_s": "8-12秒",
                    "wan22_time_s": "180-300秒",
                    "total_time_s": "188-312秒",
                    "cost_yuan": "0.09-0.16元",
                }
            }
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


# ============ 渲染Markdown剧本 ============

def render_script_md(title, genre, ref_title, templates, scene_data, rank_info=""):
    """
    将剧本数据渲染为Markdown格式（含ComfyUI配置）
    """
    now = datetime.now()
    lines = []
    
    lines.append(f"# 《{title}》- 短剧剧本（ComfyUI可执行版）\n")
    lines.append(f"> 生成时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"> 分辨率: 1080x1920 (9:16竖屏)")
    lines.append(f"> 硬件环境: RTX 4080S 32GB RAM")
    lines.append(f"> Pipeline: SDXL文生图 → Wan2.2 I2V 8秒视频 → FFmpeg合成\n")
    
    # 基本信息
    lines.append("## 基本信息\n")
    lines.append(f"- **剧名**: 《{title}》")
    lines.append(f"- **题材**: {genre}")
    lines.append(f"- **时长**: 约2分钟（150秒）")
    lines.append(f"- **分辨率**: 1080x1920 竖屏 (9:16)")
    lines.append(f"- **总场数**: 5场")
    lines.append(f"- **总视频段数**: 约15段（每场3机位）")
    if ref_title:
        lines.append(f"- **参考剧目**: 《{ref_title}》")
    if rank_info:
        lines.append(f"- **仿制依据**: {rank_info}")
    lines.append("")
    
    # 制作流程
    lines.append("## 制作流程\n")
    lines.append("```")
    lines.append("步骤1: SDXL生成分镜图 (1024x1820 → resize 1080x1920)")
    lines.append("  ↓  每张约8-12秒, 15张约2-3分钟")
    lines.append("步骤2: Wan2.2 I2V生8秒视频 (832x480输入, 输出upscale到1080P)")
    lines.append("  ↓  每段约3-5分钟, 15段约45-75分钟")
    lines.append("步骤3: FFmpeg拼接+字幕+配音")
    lines.append("  ↓  约2分钟")
    lines.append("成品: 2分钟1080P竖屏短剧")
    lines.append("```\n")
    
    # 成本估算
    lines.append("## 成本估算（RTX 4080S, 1.8元/小时）\n")
    lines.append("| 步骤 | 数量 | 单次耗时 | 单次成本 | 总耗时 | 总成本 |")
    lines.append("|------|:----:|---------|---------|--------|-------:|")
    lines.append("| SDXL分镜图 | 15张 | 8-12秒 | ~0.005元 | 2-3分钟 | 0.075元 |")
    lines.append("| Wan2.2视频 | 15段 | 3-5分钟 | ~0.15元 | 45-75分钟 | 1.5-2.25元 |")
    lines.append("| FFmpeg合成 | 1次 | 2分钟 | ~0.06元 | 2分钟 | 0.06元 |")
    lines.append("| **合计** | - | - | - | **50-80分钟** | **约1.6-2.4元** |")
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
    
    # 分场剧本（含ComfyUI配置）
    lines.append("## 分场剧本\n")
    
    fn = scene_data["female_name"]
    mn = scene_data["male_name"]
    
    for scene in scene_data["scenes"]:
        i = scene["scene_id"]
        lines.append(f"### 第{i}场：{scene['name']}（{scene['duration']}）\n")
        lines.append(f"**结构要求**: {scene['structure_desc']}\n")
        
        # 剧情内容
        if i == 1:
            lines.append(f"- **画面**: {scene_data['opening_hook']}")
            lines.append(f"- **旁白/字幕**: 「这一天，{fn}的人生彻底改变了——」")
            lines.append(f"- 💥 **爆点**: 3秒内建立核心悬念，让观众停不下来")
        elif i == 2:
            lines.append(f"- **场景**: {fn}面对{scene_data['conflict']}的处境")
            lines.append(f"- **{fn}**（倔强）:「我不会认输的。」")
            lines.append(f"- **{mn}**（冷淡/复杂）:「你还有别的选择吗？」")
            lines.append(f"- 💥 **爆点**: 矛盾建立的同时埋下伏笔，暗示{mn}的态度不简单")
        elif i == 3:
            lines.append(f"- **场景**: 冲突升级——{scene_data['conflict']}愈演愈烈")
            lines.append(f"- **反派**（嚣张）:「你以为你是谁？」")
            lines.append(f"- **{fn}**（隐忍→爆发）:「你等着。」")
            lines.append(f"- **{mn}**（暗处观察，表情复杂）")
            lines.append(f"- 💥 **爆点**: 主角被逼到绝境，观众愤怒值拉满，期待反转")
        elif i == 4:
            lines.append(f"- **场景**: {scene_data['reversal']}")
            lines.append(f"- **{mn}**（当众）:「她是我的人/我真实的身份是——」")
            lines.append(f"- 全场震惊")
            lines.append(f"- **{fn}**（震撼/泪目）:「你……一直都知道？」")
            lines.append(f"- 💥 **爆点**: 全剧最强反转，之前所有伏笔回收，观众爽感爆发")
        elif i == 5:
            lines.append(f"- **画面**: {scene_data['ending_hook']}")
            lines.append(f"- **旁白/字幕**: 「一切，才刚刚开始……」")
            lines.append(f"- 💥 **爆点**: 留下强悬念，让观众追下一集")
        
        lines.append("")
        
        # ComfyUI配置区块
        comfyui = scene.get("comfyui", {})
        if comfyui:
            lines.append(f"#### 🎬 ComfyUI配置 - 第{i}场\n")
            
            # SDXL配置
            sdxl = comfyui.get("sdxl", {})
            lines.append(f"**SDXL文生图** (生成分镜底图)\n")
            lines.append(f"```")
            lines.append(f"正向提示词:")
            lines.append(f"  {sdxl.get('prompt', '')}")
            lines.append(f"")
            lines.append(f"反向提示词:")
            lines.append(f"  {sdxl.get('negative_prompt', '')}")
            lines.append(f"")
            lines.append(f"参数配置:")
            lines.append(f"  分辨率: {sdxl.get('width', 1024)}x{sdxl.get('height', 1820)} → resize到 {sdxl.get('final_resize', {}).get('width', 1080)}x{sdxl.get('final_resize', {}).get('height', 1920)}")
            lines.append(f"  CFG Scale: {sdxl.get('cfg_scale', 7.0)}")
            lines.append(f"  Steps: {sdxl.get('steps', 30)}")
            lines.append(f"  Sampler: {sdxl.get('sampler', 'euler_ancestral')}")
            lines.append(f"  Checkpoint: {sdxl.get('checkpoint', 'sd_xl_base_1.0.safetensors')}")
            lines.append(f"  耗时: ~8-12秒/张 (4080S)")
            lines.append(f"```\n")
            
            # Wan2.2配置
            wan22 = comfyui.get("wan22_i2v", {})
            lines.append(f"**Wan2.2 图生视频** (8秒竖屏视频)\n")
            lines.append(f"```")
            lines.append(f"运动提示词:")
            lines.append(f"  {wan22.get('motion_prompt', '')}")
            lines.append(f"")
            lines.append(f"反向提示词:")
            lines.append(f"  {wan22.get('negative_prompt', '')}")
            lines.append(f"")
            lines.append(f"参数配置:")
            lines.append(f"  输入图尺寸: {wan22.get('input_resolution', '832x480')}")
            lines.append(f"  输出目标: {wan22.get('output_target', '1080x1920')}")
            lines.append(f"  帧数: {wan22.get('frames', 64)} 帧")
            lines.append(f"  FPS: {wan22.get('fps', 8)}")
            lines.append(f"  时长: {wan22.get('video_duration', '8秒')}")
            lines.append(f"  CFG Scale: {wan22.get('cfg_scale', 7.0)}")
            lines.append(f"  Steps: {wan22.get('steps', 30)}")
            lines.append(f"  Sampler: {wan22.get('sampler', 'uni_pc_bh2')}")
            lines.append(f"  Motion Strength: {wan22.get('motion_strength', 0.8)}")
            lines.append(f"  Model: {wan22.get('model', 'Wan2.1-I2V-14B-480P.safetensors')}")
            lines.append(f"  耗时: ~3-5分钟/段 (4080S)")
            lines.append(f"```\n")
            
            # 时间成本
            tc = comfyui.get("time_cost", {})
            lines.append(f"⏱ 本场耗时: SDXL {tc.get('sdxl_time_s', '')} + Wan2.2 {tc.get('wan22_time_s', '')} = **{tc.get('total_time_s', '')}**")
            lines.append(f"💰 本场成本: **{tc.get('cost_yuan', '')}**\n")
    
    # 钩子设计
    lines.append("## 钩子设计\n")
    lines.append(f"- **开头钩子**: {scene_data['opening_hook']}（3秒内抓住观众）")
    lines.append(f"- **结尾悬念**: {scene_data['ending_hook']}（引导追更下一集）")
    lines.append("")
    
    # 拍摄提示
    lines.append("## 拍摄/AI生成提示\n")
    lines.append("- 分辨率: **1080x1920 (9:16竖屏)**")
    lines.append("- SDXL生图: 1024x1820 → resize到1080x1920")
    lines.append("- Wan2.2视频: 832x480输入 → 输出upscale到1080x1920")
    lines.append("- 每场3个机位（近景/中景/远景），共15段视频")
    lines.append("- 对白精简，每句不超过15字")
    lines.append("- 开头3秒和结尾12秒为关键留存点，务必精彩")
    lines.append("- 情绪转折点配合音乐切换")
    lines.append("")
    
    # ComfyUI工作流引用
    lines.append("## ComfyUI工作流文件\n")
    lines.append("| 工作流 | 文件 | 用途 |")
    lines.append("|--------|------|------|")
    lines.append("| SDXL竖屏分镜 | `workflows/sdxl_1080p_portrait.json` | 生成1080P竖屏分镜图 |")
    lines.append("| Wan2.2 I2V | `workflows/wan22_i2v_1080p_8s.json` | 图生8秒视频 |")
    lines.append("")
    lines.append("> 💡 将workflow JSON导入ComfyUI，替换提示词节点中的`{{POSITIVE_PROMPT}}`和`{{MOTION_PROMPT}}`即可执行\n")
    
    return "\n".join(lines)


def generate_comfyui_workflow_json(title, genre, scene_data):
    """
    为每场生成可直接导入ComfyUI执行的workflow JSON
    
    返回：
        字典 {scene_id: workflow_json_string}
    """
    workflows = {}
    
    for scene in scene_data["scenes"]:
        scene_id = scene["scene_id"]
        comfyui = scene.get("comfyui", {})
        sdxl = comfyui.get("sdxl", {})
        wan22 = comfyui.get("wan22_i2v", {})
        
        # 生成SDXL工作流
        sdxl_wf_path = os.path.join(WORKFLOW_DIR, "sdxl_1080p_portrait.json")
        if os.path.exists(sdxl_wf_path):
            with open(sdxl_wf_path, "r", encoding="utf-8") as f:
                sdxl_wf = f.read()
            # 替换模板变量
            sdxl_wf = sdxl_wf.replace("{{POSITIVE_PROMPT}}", sdxl.get("prompt", ""))
            sdxl_wf = sdxl_wf.replace("{SCENE_ID}", f"{scene_id:02d}")
        
        # 生成Wan2.2工作流
        wan22_wf_path = os.path.join(WORKFLOW_DIR, "wan22_i2v_1080p_8s.json")
        if os.path.exists(wan22_wf_path):
            with open(wan22_wf_path, "r", encoding="utf-8") as f:
                wan22_wf = f.read()
            wan22_wf = wan22_wf.replace("{{MOTION_PROMPT}}", wan22.get("motion_prompt", ""))
            wan22_wf = wan22_wf.replace("{SCENE_ID}", f"{scene_id:02d}")
        
        workflows[scene_id] = {
            "scene_name": scene["name"],
            "sdxl_workflow": json.loads(sdxl_wf) if os.path.exists(sdxl_wf_path) else None,
            "wan22_workflow": json.loads(wan22_wf) if os.path.exists(wan22_wf_path) else None,
        }
    
    return workflows


# ============ 主生成函数 ============

def generate_script(rank_data, genre=None, ref_title=None, templates=None, output_dir=None, comfyui_mode=False):
    """
    生成仿制剧本
    
    参数：
        rank_data: 热度榜数据
        genre: 目标题材（None则自动选择最热题材）
        ref_title: 参考剧目（None则自动选择Top1）
        templates: 题材模板（None则自动加载）
        output_dir: 输出目录
        comfyui_mode: 是否生成ComfyUI可执行workflow JSON
    
    返回：
        (script_content, filepath, title, genre) 元组
    """
    if not templates:
        templates = load_templates()
    
    hit_analysis = analyze_hit_pattern(rank_data)
    
    if not genre:
        if hit_analysis["top_genres"]:
            genre = hit_analysis["top_genres"][0][0]
        else:
            genre = "婚恋"
    
    if genre not in templates:
        genre = "婚恋"
    
    if not ref_title:
        if hit_analysis["top_titles"]:
            ref_title = hit_analysis["top_titles"][0]
        else:
            ref_title = "热门短剧"
    
    rank_info = ""
    for item in rank_data:
        if item.get("title") == ref_title:
            rank_info = f"当日热度#{item.get('ranking', '?')}，热度{item.get('hots', '?')}"
            break
    
    title = generate_title(genre, templates, hit_analysis)
    scene_data = generate_scenes(genre, templates)
    content = render_script_md(title, genre, ref_title, templates, scene_data, rank_info)
    
    now = datetime.now()
    date_file = now.strftime("%Y-%m-%d")
    
    script_dir = Path(output_dir) if output_dir else Path(DEFAULT_SCRIPT_DIR)
    script_dir.mkdir(parents=True, exist_ok=True)
    
    safe_title = title[:10].replace("，", "").replace("、", "").replace(" ", "").replace("/", "").replace("\\", "").replace(":", "")
    safe_genre = genre.replace("/", "").replace("\\", "").replace(":", "")
    filename = f"{safe_genre}_{safe_title}_{date_file}.md"
    filepath = script_dir / filename
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    
    # ComfyUI模式下，额外输出workflow JSON
    if comfyui_mode:
        workflows = generate_comfyui_workflow_json(title, genre, scene_data)
        wf_dir = script_dir / "workflows" / f"{safe_genre}_{safe_title}_{date_file}"
        wf_dir.mkdir(parents=True, exist_ok=True)
        
        for scene_id, wf_data in workflows.items():
            # 保存SDXL工作流
            if wf_data.get("sdxl_workflow"):
                sdxl_path = wf_dir / f"scene_{scene_id:02d}_sdxl.json"
                with open(sdxl_path, "w", encoding="utf-8") as f:
                    json.dump(wf_data["sdxl_workflow"], f, ensure_ascii=False, indent=2)
            
            # 保存Wan2.2工作流
            if wf_data.get("wan22_workflow"):
                wan22_path = wf_dir / f"scene_{scene_id:02d}_wan22_i2v.json"
                with open(wan22_path, "w", encoding="utf-8") as f:
                    json.dump(wf_data["wan22_workflow"], f, ensure_ascii=False, indent=2)
        
        print(f"  📁 ComfyUI工作流已保存: {wf_dir}")
    
    return content, str(filepath), title, genre


def generate_batch_scripts(rank_data, count=5, templates=None, output_dir=None, comfyui_mode=False):
    """批量生成仿制剧本"""
    if not templates:
        templates = load_templates()
    
    hit_analysis = analyze_hit_pattern(rank_data, top_n=count)
    
    results = []
    generated_genres = set()
    
    for genre, _ in hit_analysis["top_genres"]:
        if len(results) >= count:
            break
        if genre in generated_genres or genre == "其他":
            continue
        if genre not in templates:
            continue
        
        generated_genres.add(genre)
        
        ref_title = None
        for item in rank_data:
            t = item.get("title", "")
            genres = classify_genre(t)
            if genre in genres:
                ref_title = t
                break
        
        content, filepath, script_title, g = generate_script(
            rank_data, genre=genre, ref_title=ref_title,
            templates=templates, output_dir=output_dir,
            comfyui_mode=comfyui_mode
        )
        results.append((script_title, genre, filepath))
    
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
            templates=templates, output_dir=output_dir,
            comfyui_mode=comfyui_mode
        )
        results.append((script_title, genre, filepath))
    
    return results


# ============ 独立运行入口 ============

def main():
    """独立运行时的入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="短剧仿制剧本生成 v2.0 (ComfyUI可执行版)")
    parser.add_argument("--rank-data", required=True, help="热度榜JSON文件路径")
    parser.add_argument("--script", action="store_true", help="生成仿制剧本")
    parser.add_argument("--genre", help="指定剧本题材")
    parser.add_argument("--ref", help="指定参考剧目")
    parser.add_argument("--batch", action="store_true", help="批量生成")
    parser.add_argument("--count", type=int, default=5, help="批量生成数量")
    parser.add_argument("--output", help="输出目录")
    parser.add_argument("--comfyui", action="store_true", help="生成ComfyUI可执行workflow JSON")
    
    args = parser.parse_args()
    
    with open(args.rank_data, "r", encoding="utf-8") as f:
        rank_data = json.load(f)
    
    templates = load_templates()
    
    if args.batch:
        results = generate_batch_scripts(
            rank_data, count=args.count,
            templates=templates, output_dir=args.output,
            comfyui_mode=args.comfyui
        )
        print(f"\n✅ 批量生成 {len(results)} 个剧本：")
        for title, genre, filepath in results:
            print(f"  [{genre}] 《{title}》→ {filepath}")
    elif args.script:
        content, filepath, title, genre = generate_script(
            rank_data, genre=args.genre, ref_title=args.ref,
            templates=templates, output_dir=args.output,
            comfyui_mode=args.comfyui
        )
        print(f"\n✅ 剧本已生成：")
        print(f"  题材: {genre}")
        print(f"  剧名: 《{title}》")
        print(f"  文件: {filepath}")
        print(f"  分辨率: 1080x1920 (9:16竖屏)")
        print(f"  ComfyUI工作流: {'已生成' if args.comfyui else '未生成（加 --comfyui 启用）'}")
    else:
        print("请指定 --script 或 --batch 参数")


if __name__ == "__main__":
    main()
