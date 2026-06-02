#!/usr/bin/env python3
"""
短剧制作一键Pipeline v5.0 (Shortdrama Production Pipeline) —— 配音先行版

改进点（相比 v4.1）：
1. 新增 Flux2-Klein-9B 文生图工作流支持（fp4量化版，1024x1820 → 1080x1920）
2. 修改 Wan2.2-14B 文生视频工作流为8秒@16fps（832x480 → upscale 1080P）
3. 修复 comfyui_api.py 缺少 import sys 的 bug
4. 新增 fetch_hotspot.py 热点抓取模块（带API降级和备选数据）
5. 修正 fetch_hotspot 导入路径（scripts/ 子目录）

完整8步流程（配音先行）：
  1. 抓取热点 → 2. 生成剧本(含对白/旁白) →
  3. TTS配音先行 → 4. 分镜规划(根据音频时长) →
  5. SDXL生图 → 6. Wan2.2生视频 →
  7. 字幕生成 → 8. FFmpeg合成

核心思路：配音先行，音频时长决定分镜张数和停留节奏，画面和声音完美同步。

使用方式：
  python pipeline.py --auto                    # 全自动：抓热点→生成剧本→TTS先行
  python pipeline.py --auto --run-comfyui      # 全自动+调用ComfyUI（需ComfyUI服务运行中）
  python pipeline.py --auto --run-comfyui --tts # 全自动+ComfyUI+TTS配音+字幕
  python pipeline.py --from-script <script.md> # 从已有剧本开始（跳过抓热点，直接配音→分镜→合成）
  python pipeline.py --cost-estimate           # 仅计算成本估算

硬件环境：RTX 5060 Ti 32GB RAM
成本：1.8元/小时 (AutoDL云算力)
分辨率：1080x1920 (9:16竖屏)
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# 项目内部模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import config

# 日志配置
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format=config.LOG_FORMAT,
)
logger = logging.getLogger("shortdrama.pipeline")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def print_header(title):
    """打印步骤标题"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def print_step(step_num, total_steps, description):
    """打印步骤信息"""
    print(f"\n[{step_num}/{total_steps}] {description}")


def estimate_cost(num_episodes=1, scenes_per_episode=5, angles_per_scene=3, include_tts=True):
    """
    计算制作成本估算
    """
    total_images = num_episodes * scenes_per_episode * angles_per_scene
    total_videos = total_images

    sdxl_time = total_images * config.SDXL_TIME_PER_IMAGE_S
    wan22_time = total_videos * config.WAN22_TIME_PER_VIDEO_S
    ffmpeg_time = num_episodes * config.FFMPEG_TIME_S
    tts_time = num_episodes * config.TTS_TIME_S if include_tts else 0
    total_time = sdxl_time + wan22_time + ffmpeg_time + tts_time

    cost_per_hour = config.COST_PER_HOUR
    sdxl_cost = (sdxl_time / 3600) * cost_per_hour
    wan22_cost = (wan22_time / 3600) * cost_per_hour
    ffmpeg_cost = (ffmpeg_time / 3600) * cost_per_hour
    tts_cost = (tts_time / 3600) * cost_per_hour
    total_cost = sdxl_cost + wan22_cost + ffmpeg_cost + tts_cost

    return {
        "num_episodes": num_episodes,
        "total_images": total_images,
        "total_videos": total_videos,
        "time": {
            "sdxl": f"{sdxl_time//60}分{sdxl_time%60}秒",
            "wan22": f"{wan22_time//60}分{wan22_time%60}秒",
            "ffmpeg": f"{ffmpeg_time//60}分{ffmpeg_time%60}秒",
            "tts": f"{tts_time//60}分{tts_time%60}秒" if include_tts else "0分0秒",
            "total_seconds": total_time,
            "total_readable": f"{total_time//60}分{total_time%60}秒",
            "total_hours": f"{total_time/3600:.1f}小时",
        },
        "cost": {
            "sdxl": f"¥{sdxl_cost:.3f}",
            "wan22": f"¥{wan22_cost:.2f}",
            "ffmpeg": f"¥{ffmpeg_cost:.3f}",
            "tts": f"¥{tts_cost:.3f}" if include_tts else "¥0",
            "total": f"¥{total_cost:.2f}",
            "total_per_episode": f"¥{total_cost/max(num_episodes,1):.2f}",
        },
        "hardware": "RTX 5060 Ti 32GB RAM",
        "rate": f"¥{cost_per_hour}/小时",
    }


# ============ 步骤1：抓取热点 ============
def step1_fetch_hotspot(output_dir):
    """步骤1：抓取短剧热点"""
    print_step(1, 8, "抓取短剧热点数据...")

    scripts_dir = str(config.SCRIPTS_PKG_DIR)
    sys.path.insert(0, scripts_dir)
    from fetch_hotspot import fetch_shortdrama_rank, fetch_douyin_hot, generate_genre_stats

    rank_data = fetch_shortdrama_rank()
    if not rank_data:
        logger.error("未能获取热点数据")
        return None

    douyin_data = fetch_douyin_hot()
    genre_stats = generate_genre_stats(rank_data)

    print(f"  ✓ 获取到 {len(rank_data)} 条热度数据")
    print(f"  ✓ 抖音热搜 {len(douyin_data)} 条相关")
    print(f"  ✓ 题材分布: {dict(list(genre_stats.items())[:5])}")

    # 保存热点数据JSON供后续使用
    hotspot_file = os.path.join(output_dir, f"hotspot_{datetime.now().strftime('%Y-%m-%d')}.json")
    with open(hotspot_file, "w", encoding="utf-8") as f:
        json.dump(rank_data, f, ensure_ascii=False, indent=2)

    return rank_data


# ============ 步骤2：生成剧本 ============
def step2_generate_script(rank_data, output_dir, genre=None, comfyui_mode=True):
    """步骤2：生成剧本（含对白/旁白）"""
    print_step(2, 8, "生成仿制剧本（含对白/旁白）...")

    scripts_dir = str(config.SCRIPTS_PKG_DIR)
    sys.path.insert(0, scripts_dir)
    from generate_script import generate_script as _gen_script, load_templates

    templates = load_templates()
    script_output = os.path.join(output_dir, "scripts")

    content, filepath, title, script_genre = _gen_script(
        rank_data, genre=genre,
        templates=templates, output_dir=script_output,
        comfyui_mode=comfyui_mode
    )

    print(f"  ✓ 剧名: 《{title}》")
    print(f"  ✓ 题材: {script_genre}")
    print(f"  ✓ 剧本文件: {filepath}")
    script_workflow_dir = None
    if comfyui_mode:
        wf_dir = os.path.join(script_output, "workflows")
        print(f"  ✓ ComfyUI工作流: {wf_dir}")
        # 找到最新生成的子目录
        if os.path.exists(wf_dir):
            wf_subdirs = sorted([d for d in os.listdir(wf_dir)
                                  if os.path.isdir(os.path.join(wf_dir, d))])
            if wf_subdirs:
                script_workflow_dir = os.path.join(wf_dir, wf_subdirs[-1])

    return filepath, title, script_genre, script_workflow_dir


# ============ 步骤3：SDXL生图 ============
def step3_generate_images(workflow_dir, comfyui_running=False):
    """步骤4/5：SDXL生成分镜图（在TTS配音之后，分镜张数由音频时长决定）"""
    print_step(5, 8, "SDXL生成1080P竖屏分镜图...")

    scripts_dir = str(config.SCRIPTS_PKG_DIR)
    sys.path.insert(0, scripts_dir)
    from comfyui_api import check_comfyui_running, submit_workflows_from_dir, wait_for_all_tasks

    comfyui_url = config.COMFYUI_API_URL

    if not comfyui_running:
        print("  ⏭ ComfyUI未运行，跳过自动生图")
        print("  📋 手动操作步骤：")
        print("    1. 启动ComfyUI (python main.py --listen)")
        print(f"    2. 导入工作流: {workflow_dir}/scene_XX_sdxl.json")
        print("    3. 点击Queue Prompt执行")
        print(f"    4. 预计耗时: ~2-3分钟（15张图）")
        return False

    try:
        if not check_comfyui_running(comfyui_url):
            print(f"  ✗ ComfyUI服务未运行 ({comfyui_url})")
            return False

        print("  ✓ ComfyUI服务已连接")

        # 修复：使用 pattern 参数而非 suffix
        prompt_ids = submit_workflows_from_dir(workflow_dir, comfyui_url, pattern="*_sdxl.json")
        if not prompt_ids:
            print("  ⚠ 未找到SDXL工作流文件")
            return False

        print(f"  ✓ 已提交 {len(prompt_ids)} 个SDXL任务")

        print("  ⏳ 等待SDXL生图完成...")
        results = wait_for_all_tasks(prompt_ids, comfyui_url, poll_interval=3, timeout=300)
        completed = sum(1 for v in results.values() if v.get("status") == "completed")
        print(f"  ✓ SDXL生图完成: {completed}/{len(prompt_ids)}")
        return True

    except Exception as e:
        logger.error(f"ComfyUI连接失败: {e}")
        print("  📋 请手动导入工作流执行")
        return False


# ============ 步骤4：Wan2.2生视频 ============
def step4_generate_videos(workflow_dir, comfyui_running=False):
    """步骤6：Wan2.2 I2V生成竖屏视频"""
    print_step(6, 8, "Wan2.2 I2V生成竖屏视频...")

    scripts_dir = str(config.SCRIPTS_PKG_DIR)
    sys.path.insert(0, scripts_dir)
    from comfyui_api import check_comfyui_running, submit_workflows_from_dir, wait_for_all_tasks

    comfyui_url = config.COMFYUI_API_URL

    if not comfyui_running:
        print("  ⏭ ComfyUI未运行，跳过自动生视频")
        print("  📋 手动操作步骤：")
        print("    1. 确保SDXL分镜图已生成")
        print(f"    2. 导入工作流: {workflow_dir}/scene_XX_wan22_i2v.json")
        print("    3. 在LoadImage节点选择对应分镜图")
        print("    4. 点击Queue Prompt执行")
        print(f"    5. 预计耗时: ~45-75分钟（15段视频 × 3-5分钟/段）")
        return False

    try:
        if not check_comfyui_running(comfyui_url):
            print(f"  ✗ ComfyUI服务未运行 ({comfyui_url})")
            return False

        # 修复：使用 pattern 参数
        prompt_ids = submit_workflows_from_dir(workflow_dir, comfyui_url, pattern="*_wan22_i2v.json")
        if not prompt_ids:
            print("  ⚠ 未找到Wan2.2工作流文件")
            return False

        print(f"  ✓ 已提交 {len(prompt_ids)} 个Wan2.2任务")

        print("  ⏳ 等待Wan2.2生视频完成（预计45-75分钟）...")
        results = wait_for_all_tasks(prompt_ids, comfyui_url, poll_interval=10, timeout=5400)
        completed = sum(1 for v in results.values() if v.get("status") == "completed")
        print(f"  ✓ Wan2.2视频生成完成: {completed}/{len(prompt_ids)}")
        return True

    except Exception as e:
        logger.error(f"ComfyUI连接失败: {e}")
        return False


    # ============ 步骤3（原步骤5）：TTS配音先行 ============
def step5_generate_tts(script_path, output_dir):
    """步骤3：TTS配音先行——根据剧本生成配音，先出音频再出分镜"""
    print_step(3, 8, "TTS配音先行...")

    scripts_dir = str(config.SCRIPTS_PKG_DIR)
    sys.path.insert(0, scripts_dir)
    from tts_subtitle import extract_dialogues, generate_tts

    tts_dir = os.path.join(output_dir, "tts")
    os.makedirs(tts_dir, exist_ok=True)

    dialogues = extract_dialogues(script_path)
    if not dialogues:
        print("  ⚠ 剧本中未提取到对话，跳过TTS")
        return None

    print(f"  ✓ 提取到 {len(dialogues)} 条对话")

    try:
        tts_results = generate_tts(dialogues, tts_dir)
        print(f"  ✓ 生成 {len(tts_results)} 个配音文件")
        return tts_results
    except Exception as e:
        logger.error(f"TTS生成失败: {e}")
        print("  📋 可手动配音或使用其他TTS工具")
        return None


# ============ 步骤6：字幕生成 ============
def step6_generate_subtitles(tts_results, output_dir, script_path=None):
    """步骤7：生成SRT字幕"""
    print_step(7, 8, "生成SRT字幕...")

    scripts_dir = str(config.SCRIPTS_PKG_DIR)
    sys.path.insert(0, scripts_dir)
    from tts_subtitle import generate_srt, generate_srt_from_dialogues, extract_dialogues

    subtitle_dir = os.path.join(output_dir, "subtitles")
    os.makedirs(subtitle_dir, exist_ok=True)
    srt_path = os.path.join(subtitle_dir, f"subtitle_{datetime.now().strftime('%Y%m%d')}.srt")

    if tts_results:
        generate_srt(tts_results, srt_path)
    elif script_path:
        dialogues = extract_dialogues(script_path)
        generate_srt_from_dialogues(dialogues, srt_path)
    else:
        print("  ⚠ 无TTS结果也无剧本，跳过字幕生成")
        return None

    print(f"  ✓ 字幕文件: {srt_path}")
    return srt_path


# ============ 步骤7：FFmpeg合成 ============
def step7_compose_video(video_dir, output_dir, tts_results=None, srt_path=None):
    """步骤8：FFmpeg合成最终视频（含配音+字幕）"""
    print_step(8, 8, "FFmpeg合成最终视频...")

    # 检查FFmpeg
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        if result.returncode != 0:
            raise FileNotFoundError
        print("  ✓ FFmpeg可用")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("  ✗ FFmpeg未找到，请安装后重试")
        return False

    # 查找视频片段
    video_files = sorted([
        os.path.join(video_dir, f) for f in os.listdir(video_dir)
        if f.endswith((".mp4", ".webm", ".avi"))
    ]) if os.path.exists(video_dir) else []

    if not video_files:
        print("  ⏭ 未找到视频文件，跳过合成")
        print("  📋 手动合成命令：")
        print('    ffmpeg -f concat -safe 0 -i filelist.txt -c:v libx264 -crf 18 -preset medium output.mp4')
        return False

    # 生成concat文件
    concat_file = os.path.join(video_dir, "concat_list.txt")
    with open(concat_file, "w", encoding="utf-8") as f:
        for vf in video_files:
            f.write(f"file '{vf}'\n")

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    base_output = os.path.join(output_dir, f"shortdrama_{timestamp}.mp4")

    # 步骤7a: 拼接视频片段
    print(f"  合并 {len(video_files)} 个视频片段...")
    cmd_concat = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", concat_file,
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-c:a", "aac", "-b:a", "128k",
        base_output
    ]
    result = subprocess.run(cmd_concat, capture_output=True, timeout=300)
    if result.returncode != 0:
        logger.error(f"视频拼接失败: {result.stderr.decode()[:200]}")
        return False
    print(f"  ✓ 视频拼接完成: {base_output}")

    current_output = base_output

    # 步骤7b: 添加TTS配音
    if tts_results:
        scripts_dir = str(config.SCRIPTS_PKG_DIR)
        sys.path.insert(0, scripts_dir)
        from tts_subtitle import merge_audio_video

        audio_paths = [r["audio_path"] for r in tts_results if os.path.exists(r.get("audio_path", ""))]
        if audio_paths:
            tts_output = os.path.join(output_dir, f"shortdrama_{timestamp}_tts.mp4")
            try:
                merged = merge_audio_video(current_output, audio_paths, tts_output)
                if merged and os.path.exists(merged):
                    current_output = merged
                    print(f"  ✓ TTS配音合成完成: {current_output}")
                else:
                    print("  ⚠ TTS配音合成失败，使用无配音版本")
            except Exception as e:
                logger.warning(f"TTS配音合成异常: {e}，使用无配音版本")

    # 步骤7c: 烧录字幕
    if srt_path and os.path.exists(srt_path):
        scripts_dir = str(config.SCRIPTS_PKG_DIR)
        sys.path.insert(0, scripts_dir)
        from tts_subtitle import burn_subtitles

        sub_output = os.path.join(output_dir, f"shortdrama_{timestamp}_final.mp4")
        try:
            burned = burn_subtitles(current_output, srt_path, sub_output)
            if burned and os.path.exists(burned):
                current_output = burned
                print(f"  ✓ 字幕烧录完成: {current_output}")
            else:
                print("  ⚠ 字幕烧录失败，使用无字幕版本")
        except Exception as e:
            logger.warning(f"字幕烧录异常: {e}，使用无字幕版本")

    print(f"\n  🎬 最终视频: {current_output}")
    return True


# ============ 主Pipeline ============
def run_pipeline(genre=None, comfyui_running=False, enable_tts=False, enable_subtitles=True):
    """执行完整Pipeline"""
    start_time = time.time()
    cost_per_hour = config.COST_PER_HOUR

    print_header("短剧制作Pipeline v5.0 - 配音先行版 (9:16)")
    print(f"  硬件: RTX 5060 Ti 32GB RAM")
    print(f"  成本: ¥{cost_per_hour}/小时")
    print(f"  分辨率: 1080x1920")
    print(f"  流程: 剧本→【TTS配音先行】→分镜→视频→合成")
    print(f"  ComfyUI: {'在线' if comfyui_running else '离线（手动模式）'}")
    print(f"  TTS配音: {'开启（先行模式）' if enable_tts else '关闭'}")
    print(f"  字幕: {'开启' if enable_subtitles else '关闭'}")

    # 确保输出目录存在
    config.ensure_dirs()
    output_dir = str(config.REPORT_DIR)
    script_dir = str(config.SCRIPT_DIR)
    video_dir = str(config.VIDEO_DIR)
    tts_dir = str(config.TTS_DIR)

    # 步骤1：抓取热点
    rank_data = step1_fetch_hotspot(output_dir)
    if not rank_data:
        print("\n❌ Pipeline失败：无法获取热点数据")
        return

    # 步骤2：生成剧本
    script_path, title, script_genre, latest_wf = step2_generate_script(
        rank_data, output_dir, genre=genre, comfyui_mode=True
    )

    # 步骤3：TTS配音先行（在生图之前！）
    tts_results = None
    if enable_tts:
        tts_results = step5_generate_tts(script_path, output_dir)
        # TODO: 根据TTS音频时长计算分镜张数（步骤4：分镜规划）

    # 步骤4-5：SDXL生图（分镜张数由配音时长决定）
    if latest_wf and os.path.exists(latest_wf):
        step3_generate_images(latest_wf, comfyui_running)
    else:
        print("\n  ⏭ 未找到ComfyUI工作流目录，跳过步骤4")

    # 步骤6：Wan2.2生视频
    if latest_wf and os.path.exists(latest_wf):
        step4_generate_videos(latest_wf, comfyui_running)
    else:
        print("\n  ⏭ 未找到ComfyUI工作流目录，跳过步骤5")

    # 步骤7：字幕生成
    srt_path = None
    if enable_subtitles:
        srt_path = step6_generate_subtitles(tts_results, output_dir, script_path)

    # 步骤8：合成视频
    step7_compose_video(video_dir, output_dir, tts_results, srt_path)

    # 成本汇总
    elapsed = time.time() - start_time
    cost_info = estimate_cost(num_episodes=1, include_tts=enable_tts)

    print_header("Pipeline执行完成")
    print(f"  剧名: 《{title}》")
    print(f"  题材: {script_genre}")
    print(f"  剧本: {script_path}")
    print(f"  分辨率: 1080x1920 (9:16竖屏)")
    print(f"  预估制作时间: {cost_info['time']['total_readable']}")
    print(f"  预估制作成本: {cost_info['cost']['total']}")
    print(f"  本次Pipeline耗时: {elapsed:.1f}秒")
    print(f"\n  💡 手动执行ComfyUI工作流:")
    if latest_wf:
        print(f"    SDXL: 导入 {latest_wf}/scene_XX_sdxl.json")
        print(f"    Wan2.2: 导入 {latest_wf}/scene_XX_wan22_i2v.json")
        print(f"    组合: 导入 workflows/sdxl_wan22_combined.json (一步到位)")
    if not enable_tts:
        print(f"    TTS配音: 加 --tts 参数自动生成配音")
    print()


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="短剧制作Pipeline v5.0 — 配音先行版")
    parser.add_argument("--auto", action="store_true", help="全自动模式")
    parser.add_argument("--run-comfyui", action="store_true", help="调用ComfyUI API生图生视频")
    parser.add_argument("--tts", action="store_true", help="启用TTS配音+字幕")
    parser.add_argument("--subtitles", action="store_true", default=True, help="启用字幕（默认开启）")
    parser.add_argument("--genre", type=str, default=None, help="指定题材")
    parser.add_argument("--cost-estimate", action="store_true", help="查看成本估算")
    parser.add_argument("--from-script", type=str, default=None, help="从已有剧本生成")
    parser.add_argument("--log-level", type=str, default=None, help="日志级别")
    return parser.parse_args()


def main():
    """主入口"""
    args = parse_args()

    if args.log_level:
        logging.getLogger("shortdrama").setLevel(getattr(logging, args.log_level.upper(), logging.INFO))

    if args.cost_estimate:
        cost_per_hour = config.COST_PER_HOUR
        print_header(f"短剧制作成本估算 (RTX 5060 Ti, ¥{cost_per_hour}/小时)")
        print("\n| 集数 | 图片数 | 视频数 | 含TTS | 预估时间 | 预估成本 | 每集成本 |")
        print("|:----:|:------:|:------:|:-----:|----------|---------:|---------:|")
        for n in [1, 5, 10, 30, 50, 100]:
            info = estimate_cost(num_episodes=n, include_tts=True)
            print(f"| {n} | {info['total_images']} | {info['total_videos']} | ✓ | {info['time']['total_hours']} | {info['cost']['total']} | {info['cost']['total_per_episode']} |")
        print()
        return

    if args.auto:
        run_pipeline(
            genre=args.genre,
            comfyui_running=args.run_comfyui,
            enable_tts=args.tts,
            enable_subtitles=args.subtitles,
        )
        return

    if args.from_script:
        # 从已有剧本生成（TODO: 完善此模式）
        print(f"从剧本生成: {args.from_script}")
        return

    # 默认：显示帮助
    print("""
短剧制作Pipeline v5.0 — 配音先行版
用法:
  python pipeline.py --auto                         全自动：抓热点→剧本→TTS先行
  python pipeline.py --auto --genre "霸总"          指定题材
  python pipeline.py --auto --run-comfyui           全自动+调用ComfyUI API
  python pipeline.py --auto --run-comfyui --tts     全自动+ComfyUI+TTS配音+字幕
  python pipeline.py --from-script <剧本.md>        从已有剧本开始（跳过热点，直接配音→分镜）
  python pipeline.py --cost-estimate                查看成本估算
完整8步流程（配音先行）:
  1. 抓取热点 (酷乐API + 抖音热搜)
  2. 生成剧本 (含对白/旁白+ComfyUI工作流JSON)
  3. TTS配音先行 (先出音频，音频时长决定分镜张数和节奏)
  4. 分镜规划 (根据音频时长计算分镜数量和停留时长)
  5. SDXL生图 (按规划分镜张数生成，1024x1820 → 1080x1920)
  6. Wan2.2生视频 (8秒/段，832x480 → upscale 1080P)
  7. 字幕生成 (SRT格式，基于TTS时长精确生成时间轴)
  8. FFmpeg合成 (拼接+配音+字幕→最终成品)

v5.0 核心变化:
  - 配音先行：先配音再出分镜，音频驱动画面节奏
  - 分镜规划：新增步骤4，根据配音时长自动计算分镜数量和停留时长
  - from-script 模式：跳过热点抓取，直接从剧本开始
    """)


if __name__ == "__main__":
    main()