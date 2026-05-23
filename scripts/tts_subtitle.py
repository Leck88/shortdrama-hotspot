#!/usr/bin/env python3
"""
TTS配音 & 字幕生成模块 (TTS & Subtitle Generator)

功能概述：
1. 从Markdown剧本中提取对话列表（角色、台词、情感、场次）
2. 使用edge-tts为每个角色生成配音MP3
3. 根据对话时长生成SRT字幕文件
4. 使用FFmpeg将字幕烧录到视频中
5. 将多个配音片段按时间轴合并到视频中

依赖：
  - edge-tts (pip install edge-tts)
  - ffmpeg (系统PATH中可用)

使用方式：
  from tts_subtitle import extract_dialogues, generate_tts, generate_srt, burn_subtitles, merge_audio_video

  dialogues = extract_dialogues("script.md")
  tts_results = generate_tts(dialogues, "./output/tts")
  srt_path = generate_srt(tts_results, "./output/sub.srt")
  final = merge_audio_video("video.mp4", [r["audio_path"] for r in tts_results], "./output/final.mp4")
  burn_subtitles(final, srt_path, "./output/final_with_sub.mp4")
"""

import asyncio
import os
import re
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from typing import Optional

# 项目内部模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config

# Python解释器路径（用于edge-tts的异步通信）
PYTHON_EXE = os.environ.get(
    "SHORTDRAMA_PYTHON",
    os.sys.executable  # 默认使用当前 Python 解释器，不再硬编码路径
)

# 默认语音配置
DEFAULT_VOICE_FEMALE = "zh-CN-XiaoxiaoNeural"
DEFAULT_VOICE_MALE = "zh-CN-YunxiNeural"
DEFAULT_VOICE_NARRATOR = "zh-CN-YunjianNeural"  # 旁白用男声

# 字幕样式
SUBTITLE_STYLE = {
    "fontname": "Microsoft YaHei",
    "fontsize": 24,
    "primary_colour": "&H00FFFFFF",   # 白色
    "outline_colour": "&H00000000",   # 黑色描边
    "outline": 2,
    "alignment": 2,                    # 底部居中
    "margin_v": 30,                    # 底部边距
}


# ============ 对话提取 ============

def extract_dialogues(script_md_path: str) -> list[dict]:
    """
    从Markdown剧本中提取对话列表

    解析规则：
    - **角色名**（情感）:「台词内容」  -> 角色对话
    - **旁白/字幕**:「内容」          -> 旁白
    - - **画面**: xxx                -> 动作/画面描述（跳过）

    参数：
        script_md_path: Markdown剧本文件路径

    返回：
        对话列表 [{"scene": 1, "role": "苏晚", "text": "我不会认输的", "emotion": "倔强"}, ...]
    """
    with open(script_md_path, "r", encoding="utf-8") as f:
        content = f.read()

    dialogues = []
    current_scene = 0

    lines = content.split("\n")
    for line in lines:
        line = line.strip()
        # 去掉 Markdown 列表前缀（- 或 •），统一为 **角色名** 格式
        line = re.sub(r"^[-•]\s+", "", line)

        # 检测场次标记：### 第X场
        scene_match = re.match(r"###\s*第(\d+)场", line)
        if scene_match:
            current_scene = int(scene_match.group(1))
            continue

        # 模式1：**角色名**（情感）:「台词」 或 **角色名**（情感）：「台词」
        # 支持半角:和全角：冒号，支持「」『』""引号
        dialogue_match = re.match(
            r"\*\*(.+?)\*\*[（(](.+?)[）)]\s*[:：]\s*[「『\"\u201c](.+?)[」』\"\u201d]",
            line
        )
        if dialogue_match:
            role = dialogue_match.group(1).strip()
            emotion = dialogue_match.group(2).strip()
            text = dialogue_match.group(3).strip()
            dialogues.append({
                "scene": current_scene,
                "role": role,
                "text": text,
                "emotion": emotion,
            })
            continue

        # 模式2：**角色名**（情感）: 台词 （无引号变体兜底）
        dialogue_match2 = re.match(
            r"\*\*(.+?)\*\*[（(](.+?)[）)]\s*[:：]\s*(.+)",
            line
        )
        if dialogue_match2:
            role = dialogue_match2.group(1).strip()
            emotion = dialogue_match2.group(2).strip()
            text = dialogue_match2.group(3).strip().strip('「」『』""\u201c\u201d\u0022')
            if text and not text.startswith(('画面', '场景', '爆点', '结构')):
                dialogues.append({
                    "scene": current_scene,
                    "role": role,
                    "text": text,
                    "emotion": emotion,
                })
            continue

        # 模式3：**旁白/字幕**:「内容」 或 **旁白/字幕**：「内容」
        # 支持 "旁白" "字幕" "旁白/字幕" 三种写法
        narrator_match = re.match(
            r"\*\*(?:旁白|字幕|旁白/字幕)\*\*\s*[:：]\s*[「『\"\u201c](.+?)[」』\"\u201d]",
            line
        )
        if narrator_match:
            text = narrator_match.group(1).strip()
            dialogues.append({
                "scene": current_scene,
                "role": "旁白",
                "text": text,
                "emotion": "叙述",
            })
            continue

        # 模式4：**角色名**（情感） -> 单独一行的动作描述，不含台词（跳过）
        # 例如: **陆衍**（暗处观察，表情复杂）

    # 为没有场次信息的对话分配场景0
    for d in dialogues:
        if d["scene"] == 0:
            d["scene"] = 1

    print(f"  [TTS] 从剧本中提取到 {len(dialogues)} 条对话")
    return dialogues


# ============ TTS配音生成 ============

async def _generate_single_tts(text: str, voice: str, output_path: str, rate: str = "+0%", volume: str = "+0%") -> int:
    """
    使用edge-tts生成单条配音

    参数：
        text: 要转换的文本
        voice: 语音名称
        output_path: 输出MP3文件路径
        rate: 语速调整 (如 "+20%", "-10%")
        volume: 音量调整

    返回：
        音频时长（毫秒）
    """
    import edge_tts

    communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume)
    await communicate.save(output_path)

    # 使用ffprobe获取音频时长（如果可用）
    duration_ms = _get_audio_duration_ms(output_path)

    return duration_ms


def _get_audio_duration_ms(audio_path: str) -> int:
    """
    获取音频文件时长（毫秒）

    优先使用ffprobe，否则使用edge-tts内嵌方法估算
    """
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                audio_path
            ],
            capture_output=True, timeout=10, text=True
        )
        if result.returncode == 0:
            import json
            info = json.loads(result.stdout)
            duration_s = float(info.get("format", {}).get("duration", 0))
            return int(duration_s * 1000)
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, KeyError):
        pass

    # 回退方案：基于edge-tts的码率估算（约32kbps）
    try:
        file_size = os.path.getsize(audio_path)
        # 32kbps = 4000 bytes/second
        estimated_duration_s = file_size / 4000
        return int(estimated_duration_s * 1000)
    except OSError:
        return 3000  # 默认3秒


def _select_voice(role: str, voice_female: str, voice_male: str, voice_narrator: str = DEFAULT_VOICE_NARRATOR) -> str:
    """根据角色名选择语音"""
    if role == "旁白":
        return voice_narrator

    # 女性角色关键词
    female_keywords = ["女主", "苏晚", "林念", "沈清", "顾念", "叶棠", "温如言", "江璃", "白鹿",
                       "婆婆", "闺蜜", "女", "妈", "姐", "妹", "嫂", "婶", "姨", "姑姑"]
    # 男性角色关键词
    male_keywords = ["男主", "陆衍", "顾深", "傅修", "沈墨", "萧凛", "霍渊", "裴峥", "封诀",
                     "反派", "男", "爸", "哥", "弟", "叔", "伯", "爷"]

    for kw in female_keywords:
        if kw in role:
            return voice_female

    for kw in male_keywords:
        if kw in role:
            return voice_male

    # 默认使用女声
    return voice_female


def _emotion_to_rate(emotion: str) -> str:
    """
    将情感标注转换为edge-tts语速调整

    常见情感：倔强、愤怒、冷淡、复杂、嚣张、震撼、泪目、叙述
    """
    emotion_rate_map = {
        "愤怒": "+30%",
        "嚣张": "+20%",
        "倔强": "+10%",
        "冷淡": "-10%",
        "复杂": "-5%",
        "震撼": "+15%",
        "泪目": "-15%",
        "隐忍": "-10%",
        "爆发": "+25%",
        "叙述": "+0%",
        "温柔": "-5%",
        "坚定": "+5%",
    }
    return emotion_rate_map.get(emotion, "+0%")


def generate_tts(
    dialogues: list[dict],
    output_dir: str,
    voice_female: str = DEFAULT_VOICE_FEMALE,
    voice_male: str = DEFAULT_VOICE_MALE,
) -> list[dict]:
    """
    使用edge-tts为每个角色生成配音MP3

    参数：
        dialogues: 对话列表（由extract_dialogues返回）
        output_dir: 配音文件输出目录
        voice_female: 女声语音名称
        voice_male: 男声语音名称

    返回：
        TTS结果列表 [{"scene": 1, "role": "苏晚", "text": "...", "emotion": "倔强",
                     "audio_path": "...", "duration_ms": 2340, "voice": "zh-CN-XiaoxiaoNeural"}, ...]
    """
    os.makedirs(output_dir, exist_ok=True)

    results = []
    tasks = []

    async def _process_all():
        for i, d in enumerate(dialogues):
            scene = d["scene"]
            role = d["role"]
            text = d["text"]
            emotion = d.get("emotion", "叙述")

            voice = _select_voice(role, voice_female, voice_male)
            rate = _emotion_to_rate(emotion)

            # 生成文件名: scene_01_role_苏晚_001.mp3
            safe_role = re.sub(r'[\\/:*?"<>|]', '', role)
            filename = f"scene_{scene:02d}_{safe_role}_{i+1:03d}.mp3"
            audio_path = os.path.join(output_dir, filename)

            print(f"  [TTS] 生成配音: [{scene}] {role}({emotion}): {text[:20]}...")

            duration_ms = await _generate_single_tts(text, voice, audio_path, rate=rate)

            results.append({
                "scene": scene,
                "role": role,
                "text": text,
                "emotion": emotion,
                "audio_path": os.path.abspath(audio_path),
                "duration_ms": duration_ms,
                "voice": voice,
            })

    # 运行异步TTS生成
    try:
        asyncio.run(_process_all())
    except RuntimeError:
        # 如果已有事件循环在运行，使用nest_asyncio或新线程
        import threading
        thread = threading.Thread(target=asyncio.run, args=(_process_all(),))
        thread.start()
        thread.join(timeout=300)

    total_duration = sum(r["duration_ms"] for r in results)
    print(f"  [TTS] 共生成 {len(results)} 条配音，总时长 {total_duration/1000:.1f} 秒")

    return results


# ============ SRT字幕生成 ============

def _format_srt_time(ms: int) -> str:
    """
    将毫秒转换为SRT时间格式 HH:MM:SS,mmm

    参数：
        ms: 毫秒数

    返回：
        SRT格式时间字符串
    """
    hours = ms // 3600000
    ms %= 3600000
    minutes = ms // 60000
    ms %= 60000
    seconds = ms // 1000
    milliseconds = ms % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def generate_srt(
    tts_results: list[dict],
    output_path: str,
    gap_ms: int = 500,
    start_offset_ms: int = 0,
) -> str:
    """
    根据TTS结果生成SRT字幕文件

    每条对话的起止时间基于其音频时长，对话间有间隔。

    参数：
        tts_results: TTS生成结果列表（由generate_tts返回）
        output_path: SRT文件输出路径
        gap_ms: 对话之间的间隔（毫秒），默认500ms
        start_offset_ms: 字幕起始偏移（毫秒），默认0

    返回：
        SRT文件路径
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # 按场次和顺序排列
    sorted_results = sorted(tts_results, key=lambda x: (x["scene"], tts_results.index(x)))

    current_time_ms = start_offset_ms
    srt_entries = []

    for i, item in enumerate(sorted_results):
        start_ms = current_time_ms
        duration_ms = item["duration_ms"]
        end_ms = start_ms + duration_ms

        text = item["text"]
        role = item["role"]

        # SRT条目格式
        srt_entry = f"{i + 1}\n"
        srt_entry += f"{_format_srt_time(start_ms)} --> {_format_srt_time(end_ms)}\n"
        # 角色名+台词（旁白不加角色名前缀）
        if role == "旁白":
            srt_entry += f"{text}\n"
        else:
            srt_entry += f"{text}\n"
        srt_entry += "\n"

        srt_entries.append(srt_entry)

        # 下一条对话的起始时间 = 当前结束 + 间隔
        current_time_ms = end_ms + gap_ms

    # 写入SRT文件
    with open(output_path, "w", encoding="utf-8-sig") as f:
        f.writelines(srt_entries)

    total_duration_s = current_time_ms / 1000
    print(f"  [SRT] 字幕文件已生成: {output_path}")
    print(f"  [SRT] 共 {len(srt_entries)} 条字幕，总时长 {total_duration_s:.1f} 秒")

    return os.path.abspath(output_path)


def generate_srt_from_dialogues(
    dialogues: list[dict],
    output_path: str,
    avg_duration_per_char_ms: int = 200,
    gap_ms: int = 500,
    start_offset_ms: int = 0,
) -> str:
    """
    直接从对话列表生成SRT字幕（不需要先TTS，用于预估场景）

    参数：
        dialogues: 对话列表
        output_path: SRT文件输出路径
        avg_duration_per_char_ms: 每字平均时长（毫秒），中文约200ms/字
        gap_ms: 对话间隔（毫秒）
        start_offset_ms: 字幕起始偏移（毫秒）

    返回：
        SRT文件路径
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    current_time_ms = start_offset_ms
    srt_entries = []

    for i, d in enumerate(dialogues):
        text = d["text"]
        role = d["role"]

        # 根据字数估算时长
        char_count = len(text)
        duration_ms = max(char_count * avg_duration_per_char_ms, 1500)  # 最少1.5秒

        start_ms = current_time_ms
        end_ms = start_ms + duration_ms

        srt_entry = f"{i + 1}\n"
        srt_entry += f"{_format_srt_time(start_ms)} --> {_format_srt_time(end_ms)}\n"
        if role == "旁白":
            srt_entry += f"{text}\n"
        else:
            srt_entry += f"{text}\n"
        srt_entry += "\n"

        srt_entries.append(srt_entry)
        current_time_ms = end_ms + gap_ms

    with open(output_path, "w", encoding="utf-8-sig") as f:
        f.writelines(srt_entries)

    print(f"  [SRT] 字幕文件已生成（预估时长）: {output_path}")
    return os.path.abspath(output_path)


# ============ 字幕烧录 ============

def burn_subtitles(
    video_path: str,
    srt_path: str,
    output_path: str,
    font_name: str = SUBTITLE_STYLE["fontname"],
    font_size: int = SUBTITLE_STYLE["fontsize"],
    primary_colour: str = SUBTITLE_STYLE["primary_colour"],
    outline_colour: str = SUBTITLE_STYLE["outline_colour"],
    outline_width: int = SUBTITLE_STYLE["outline"],
    alignment: int = SUBTITLE_STYLE["alignment"],
    margin_v: int = SUBTITLE_STYLE["margin_v"],
) -> str:
    """
    使用FFmpeg将字幕烧录到视频中

    使用subtitles滤镜将SRT字幕硬烧到视频画面上。
    字幕样式：白色字体、黑色描边、底部居中、字号24。

    参数：
        video_path: 输入视频文件路径
        srt_path: SRT字幕文件路径
        output_path: 输出视频文件路径
        font_name: 字体名称
        font_size: 字体大小
        primary_colour: 主颜色（ASS格式）
        outline_colour: 描边颜色（ASS格式）
        outline_width: 描边宽度
        alignment: 对齐方式（2=底部居中）
        margin_v: 垂直边距

    返回：
        输出视频文件路径
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # Windows路径转义：SRT路径中的冒号和反斜杠需要特殊处理
    # FFmpeg subtitles滤镜要求路径使用正斜杠，且冒号需要转义
    srt_path_escaped = srt_path.replace("\\", "/").replace(":", "\\:")

    # 构建subtitles滤镜参数
    subtitle_filter = (
        f"subtitles='{srt_path_escaped}'"
        f":force_style='FontName={font_name},FontSize={font_size}"
        f",PrimaryColour={primary_colour},OutlineColour={outline_colour}"
        f",Outline={outline_width},Alignment={alignment}"
        f",MarginV={margin_v}'"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", subtitle_filter,
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-c:a", "copy",  # 音频直接复制，不重新编码
        output_path
    ]

    print(f"  [字幕烧录] 烧录字幕到视频...")
    print(f"  [字幕烧录] 输入: {video_path}")
    print(f"  [字幕烧录] 字幕: {srt_path}")

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=600, text=True)
        if result.returncode == 0:
            print(f"  [字幕烧录] 完成: {output_path}")
            return os.path.abspath(output_path)
        else:
            # 尝试备用方案：使用ass字幕格式
            print(f"  [字幕烧录] subtitles滤镜失败，尝试ass格式...")
            return _burn_subtitles_with_ass(video_path, srt_path, output_path,
                                             font_name, font_size, primary_colour,
                                             outline_colour, outline_width, alignment, margin_v)
    except FileNotFoundError:
        print("  [字幕烧录] 错误：FFmpeg未找到，请确保已安装并添加到PATH")
        raise
    except subprocess.TimeoutExpired:
        print("  [字幕烧录] 错误：FFmpeg处理超时")
        raise


def _burn_subtitles_with_ass(
    video_path: str,
    srt_path: str,
    output_path: str,
    font_name: str,
    font_size: int,
    primary_colour: str,
    outline_colour: str,
    outline_width: int,
    alignment: int,
    margin_v: int,
) -> str:
    """备用方案：将SRT转为ASS格式后烧录"""
    ass_path = srt_path.replace(".srt", ".ass")

    # 转换SRT到ASS
    _srt_to_ass(srt_path, ass_path, font_name, font_size, primary_colour,
                outline_colour, outline_width, alignment, margin_v)

    # Windows路径转义
    ass_path_escaped = ass_path.replace("\\", "/").replace(":", "\\:")

    subtitle_filter = f"ass='{ass_path_escaped}'"

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", subtitle_filter,
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-c:a", "copy",
        output_path
    ]

    result = subprocess.run(cmd, capture_output=True, timeout=600, text=True)
    if result.returncode == 0:
        print(f"  [字幕烧录] ASS烧录完成: {output_path}")
        return os.path.abspath(output_path)
    else:
        raise RuntimeError(f"FFmpeg ASS字幕烧录失败: {result.stderr[:500]}")


def _srt_to_ass(
    srt_path: str,
    ass_path: str,
    font_name: str,
    font_size: int,
    primary_colour: str,
    outline_colour: str,
    outline_width: int,
    alignment: int,
    margin_v: int,
) -> None:
    """将SRT字幕文件转换为ASS格式"""
    # ASS颜色转换：&H00FFFFFF (BGR) -> &H00FFFFFF (ASS也用BGR)
    # ASS的对齐方式：2=底部居中

    ass_header = f"""[Script Info]
Title: Shortdrama Subtitles
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{primary_colour},&H000000FF,{outline_colour},&H00000000,0,0,0,0,100,100,0,0,1,{outline_width},0,{alignment},10,10,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    # 读取SRT并转换
    with open(srt_path, "r", encoding="utf-8-sig") as f:
        srt_content = f.read()

    events = []
    # 解析SRT块
    blocks = re.split(r"\n\n+", srt_content.strip())
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue

        # 跳过序号行
        time_line = lines[1]
        text_lines = lines[2:]

        # 解析时间
        time_match = re.match(
            r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})",
            time_line
        )
        if not time_match:
            continue

        g = time_match.groups()
        start_time = f"{g[0]}:{g[1]}:{g[2]}.{g[3]}"  # SRT用逗号，ASS用点
        end_time = f"{g[4]}:{g[5]}:{g[6]}.{g[7]}"

        text = "\\N".join(text_lines)  # ASS换行符

        events.append(f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}")

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(ass_header)
        f.write("\n".join(events))

    print(f"  [ASS] SRT已转换为ASS: {ass_path}")


# ============ 音视频合并 ============

def merge_audio_video(
    video_path: str,
    audio_paths: list[str],
    output_path: str,
    gap_ms: int = 500,
    start_offset_ms: int = 0,
) -> str:
    """
    将多个配音片段按时间轴合并到视频中

    处理流程：
    1. 使用ffmpeg将多个音频片段按时间轴合并为一条完整音轨
    2. 将合并后的音轨叠加到视频上（保留原视频音轨）

    参数：
        video_path: 输入视频文件路径
        audio_paths: 配音MP3文件路径列表（按顺序排列）
        output_path: 输出视频文件路径
        gap_ms: 配音片段之间的间隔（毫秒）
        start_offset_ms: 第一条配音的起始偏移（毫秒）

    返回：
        输出视频文件路径
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    if not audio_paths:
        print("  [合并] 无配音文件，直接复制视频")
        import shutil
        shutil.copy2(video_path, output_path)
        return os.path.abspath(output_path)

    # 方法：使用ffmpeg的amerge/amix滤镜
    # 先将所有音频合并为一条完整音轨，再与视频合并

    # 创建ffmpeg concat文件，为每个音频指定延迟
    temp_dir = os.path.join(os.path.dirname(output_path), "_temp_audio")
    os.makedirs(temp_dir, exist_ok=True)

    try:
        # Step 1: 获取每个音频的时长
        durations = []
        for ap in audio_paths:
            dur = _get_audio_duration_ms(ap)
            durations.append(dur)

        # Step 2: 构建ffmpeg复杂滤镜
        # 为每个音频添加adelay，然后amix混合

        # 输入文件列表
        input_args = ["-i", video_path]
        for ap in audio_paths:
            input_args.extend(["-i", ap])

        # 计算每个音频的延迟时间
        current_delay = start_offset_ms
        delay_filters = []
        mix_inputs = []

        for i, (ap, dur) in enumerate(zip(audio_paths, durations)):
            delay_filter = f"[{i+1}:a]adelay={current_delay}|{current_delay}[a{i}]"
            delay_filters.append(delay_filter)
            mix_inputs.append(f"[a{i}]")
            current_delay += dur + gap_ms

        # 构建amix滤镜
        n_inputs = len(audio_paths)
        mix_filter = f"{''.join(mix_inputs)}amix=inputs={n_inputs}:duration=longest:dropout_transition=0[aout]"

        filter_complex = ";".join(delay_filters) + ";" + mix_filter

        cmd = [
            "ffmpeg", "-y",
            *input_args,
            "-filter_complex", filter_complex,
            "-map", "0:v",          # 视频流来自第一个输入
            "-map", "[aout]",       # 混合后的音频
            "-c:v", "copy",         # 视频直接复制
            "-c:a", "aac", "-b:a", "128k",  # 音频编码为AAC
            "-shortest",
            output_path
        ]

        print(f"  [合并] 合并 {len(audio_paths)} 条配音到视频...")
        result = subprocess.run(cmd, capture_output=True, timeout=600, text=True)

        if result.returncode == 0:
            print(f"  [合并] 完成: {output_path}")
            return os.path.abspath(output_path)
        else:
            # 回退方案：先合并所有音频为单文件，再叠加
            print(f"  [合并] amix方式失败，尝试逐条合并...")
            return _merge_audio_video_fallback(video_path, audio_paths, output_path,
                                                durations, gap_ms, start_offset_ms)

    finally:
        # 清理临时文件
        import shutil
        if os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass


def _merge_audio_video_fallback(
    video_path: str,
    audio_paths: list[str],
    output_path: str,
    durations: list[int],
    gap_ms: int,
    start_offset_ms: int,
) -> str:
    """备用方案：逐条合并音频到视频"""
    # Step 1: 先将所有音频拼接为一条连续音轨
    temp_dir = os.path.join(os.path.dirname(output_path), "_temp_audio")
    os.makedirs(temp_dir, exist_ok=True)

    try:
        # 在每段音频之间添加静音间隔
        concat_list_path = os.path.join(temp_dir, "concat_list.txt")
        with open(concat_list_path, "w", encoding="utf-8") as f:
            current_delay = 0
            for i, (ap, dur) in enumerate(zip(audio_paths, durations)):
                if i == 0 and start_offset_ms > 0:
                    # 在开头添加静音
                    silence_path = os.path.join(temp_dir, f"silence_start.wav")
                    _generate_silence(start_offset_ms, silence_path)
                    f.write(f"file '{silence_path.replace(chr(92), '/')}'\n")

                f.write(f"file '{ap.replace(chr(92), '/')}'\n")

                # 在音频之间添加静音间隔
                if i < len(audio_paths) - 1 and gap_ms > 0:
                    silence_path = os.path.join(temp_dir, f"silence_{i}.wav")
                    _generate_silence(gap_ms, silence_path)
                    f.write(f"file '{silence_path.replace(chr(92), '/')}'\n")

        # 合并所有音频
        merged_audio = os.path.join(temp_dir, "merged_audio.mp3")
        cmd_concat = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_list_path,
            "-c:a", "libmp3lame", "-b:a", "128k",
            merged_audio
        ]
        result = subprocess.run(cmd_concat, capture_output=True, timeout=120, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"音频合并失败: {result.stderr[:500]}")

        # Step 2: 将合并音频叠加到视频
        cmd_merge = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", merged_audio,
            "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=shortest:dropout_transition=0[aout]",
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest",
            output_path
        ]
        result = subprocess.run(cmd_merge, capture_output=True, timeout=600, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"音视频合并失败: {result.stderr[:500]}")

        print(f"  [合并] 备用方案完成: {output_path}")
        return os.path.abspath(output_path)

    finally:
        import shutil
        if os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass


def _generate_silence(duration_ms: int, output_path: str) -> None:
    """生成指定时长的静音WAV文件"""
    duration_s = duration_ms / 1000.0
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono",
        "-t", str(duration_s),
        "-c:a", "pcm_s16le",
        output_path
    ]
    subprocess.run(cmd, capture_output=True, timeout=30)


# ============ 便捷组合函数 ============

def generate_tts_and_srt(
    script_md_path: str,
    output_dir: str,
    voice_female: str = DEFAULT_VOICE_FEMALE,
    voice_male: str = DEFAULT_VOICE_MALE,
) -> tuple[list[dict], str]:
    """
    一站式生成TTS配音和SRT字幕

    参数：
        script_md_path: Markdown剧本文件路径
        output_dir: 输出目录
        voice_female: 女声语音
        voice_male: 男声语音

    返回：
        (tts_results, srt_path) 元组
    """
    # 提取对话
    dialogues = extract_dialogues(script_md_path)

    # 生成配音
    tts_dir = os.path.join(output_dir, "tts")
    tts_results = generate_tts(dialogues, tts_dir, voice_female, voice_male)

    # 生成字幕
    srt_path = os.path.join(output_dir, "subtitles.srt")
    srt_path = generate_srt(tts_results, srt_path)

    return tts_results, srt_path


def compose_final_video(
    video_path: str,
    tts_results: list[dict],
    srt_path: str,
    output_dir: str,
    filename_prefix: str = "shortdrama_final",
) -> str:
    """
    一站式合成最终视频（配音+字幕）

    参数：
        video_path: 原始视频文件路径
        tts_results: TTS生成结果
        srt_path: SRT字幕文件路径
        output_dir: 输出目录
        filename_prefix: 输出文件名前缀

    返回：
        最终视频文件路径
    """
    os.makedirs(output_dir, exist_ok=True)

    # Step 1: 合并配音到视频
    audio_paths = [r["audio_path"] for r in tts_results]
    dubbed_video = os.path.join(output_dir, f"{filename_prefix}_dubbed.mp4")
    dubbed_video = merge_audio_video(video_path, audio_paths, dubbed_video)

    # Step 2: 烧录字幕
    final_video = os.path.join(output_dir, f"{filename_prefix}_final.mp4")
    final_video = burn_subtitles(dubbed_video, srt_path, final_video)

    return final_video


# ============ 独立运行入口 ============

def main():
    """独立运行时的入口"""
    import argparse

    parser = argparse.ArgumentParser(description="TTS配音 & 字幕生成模块")
    parser.add_argument("--script", required=True, help="Markdown剧本文件路径")
    parser.add_argument("--output", required=True, help="输出目录")
    parser.add_argument("--voice-female", default=DEFAULT_VOICE_FEMALE, help="女声语音")
    parser.add_argument("--voice-male", default=DEFAULT_VOICE_MALE, help="男声语音")
    parser.add_argument("--video", help="视频文件路径（用于合并配音和烧录字幕）")
    parser.add_argument("--skip-tts", action="store_true", help="跳过TTS，仅生成预估字幕")

    args = parser.parse_args()

    print("=" * 50)
    print("  TTS配音 & 字幕生成")
    print("=" * 50)

    os.makedirs(args.output, exist_ok=True)

    if args.skip_tts:
        # 仅生成预估字幕
        dialogues = extract_dialogues(args.script)
        srt_path = os.path.join(args.output, "subtitles_estimated.srt")
        generate_srt_from_dialogues(dialogues, srt_path)
        return

    # 完整流程
    tts_results, srt_path = generate_tts_and_srt(
        args.script, args.output,
        voice_female=args.voice_female,
        voice_male=args.voice_male,
    )

    if args.video:
        final = compose_final_video(args.video, tts_results, srt_path, args.output)
        print(f"\n最终视频: {final}")
    else:
        print(f"\n配音文件: {os.path.join(args.output, 'tts')}")
        print(f"字幕文件: {srt_path}")


if __name__ == "__main__":
    main()
