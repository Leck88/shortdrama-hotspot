#!/usr/bin/env python3
"""
短剧制作一键Pipeline v5.2 (Shortdrama Production Pipeline) —— 租算力+SDXL+LoRA锁人+5秒分段版

完整8步流程（配音先行 + SDXL文生图 + LoRA锁人 + Wan2.2图生视频）：
  1. 抓取热点 → 2. 生成剧本(含对白/旁白+SDXL提示词+LoRA锁人词) →
  3. TTS配音先行 → 4. SDXL文生图（租算力4090，LoRA锁人，每场3张抽卡） →
  5. 人工筛选分镜图 → 6. Wan2.2 图生视频（5秒/段，尾帧续写） →
  7. 字幕生成 → 8. FFmpeg拼接合成

核心思路：
  - SDXL文生图自动化（租算力跑），LoRA锁人保证人物一致性
  - 配音先行，音频时长决定分镜张数和停留节奏
  - 图生视频每段固定5秒，尾帧接力续写下一段，交叉淡化拼接
  - 租算力跑（RTX 4090/5090），FP16直出

使用方式：
  python pipeline.py --auto                    # 全自动：抓热点→剧本→TTS先行
  python pipeline.py --auto --run-comfyui      # 全自动+SDXL文生图+Wan2.2生视频
  python pipeline.py --auto --run-comfyui --tts # 全自动+全套
  python pipeline.py --from-script <script.md> # 从已有剧本开始
  python pipeline.py --cost-estimate           # 仅计算成本估算

硬件环境：云GPU RTX 4090 24GB（AutoDL/极智算）
成本：约 ¥4-8/小时 (4090租赁)
分辨率：输入图 → Wan2.2 832x480 → 可选 upscale 至 1080P
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

    # 文生图+图生视频成本
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
            "sdxl": f"¥{sdxl_cost:.2f}",
            "wan22": f"¥{wan22_cost:.2f}",
            "ffmpeg": f"¥{ffmpeg_cost:.3f}",
            "tts": f"¥{tts_cost:.3f}" if include_tts else "¥0",
            "total": f"¥{total_cost:.2f}",
            "total_per_episode": f"¥{total_cost/max(num_episodes,1):.2f}",
        },
        "hardware": "云GPU RTX 4090 24GB (AutoDL/极智算)",
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


# ============ 步骤4：SDXL文生图（租算力+LoRA锁人） ============
def step4_generate_images(script_path, output_dir, comfyui_running=False):
    """步骤4：SDXL文生图（租算力4090，LoRA锁人，每场3张抽卡）"""
    print_step(4, 8, "SDXL文生图（LoRA锁人）...")

    scripts_dir = str(config.SCRIPTS_PKG_DIR)
    sys.path.insert(0, scripts_dir)
    from generate_images import generate_storyboard_images

    storyboard_dir = str(config.STORYBOARD_DIR)

    if not comfyui_running:
        print("  ⏭ ComfyUI未运行，跳过自动生图")
        print("  📋 手动操作步骤：")
        print("    1. 启动租算力机上的 ComfyUI")
        print(f"    2. 设置 COMFYUI_API_URL 指向租算力机")
        print(f"    3. 运行: python scripts/generate_images.py --script {script_path}")
        print(f"    4. 或: python pipeline.py --auto --run-comfyui")
        return []

    try:
        lora_params = {
            "lora_name": config.LORA_NAME,
            "strength_model": config.LORA_STRENGTH,
            "strength_clip": config.LORA_STRENGTH,
        }
        ipadapter_params = None
        if config.REFERENCE_FACE_IMAGE:
            ipadapter_params = {"reference_image": config.REFERENCE_FACE_IMAGE}

        images = generate_storyboard_images(
            script_path=script_path,
            output_dir=storyboard_dir,
            comfyui_url=config.COMFYUI_API_URL,
            lora_params=lora_params,
            ipadapter_params=ipadapter_params,
            batch_per_scene=config.SDXL_BATCH_PER_SCENE,
        )

        if images:
            print(f"  ✅ 共生成 {len(images)} 张分镜图")
            print(f"  📁 输出: {storyboard_dir}")
            print(f"  💡 下一步: 人工筛选最优图片，重命名为 scene_XX_selected.png")
        else:
            print("  ⚠ 未生成图片，后续步骤将使用空图片列表")

        return images

    except Exception as e:
        logger.error(f"文生图失败: {e}")
        print("  ✗ 文生图失败，请检查 ComfyUI 连接和 LoRA 模型")
        return []


# ============ 步骤4：Wan2.2生视频（5秒/段） ============
def step4_generate_videos(workflow_dir, comfyui_running=False):
    """步骤5：Wan2.2 I2V生成5秒竖屏视频"""
    print_step(6, 8, "Wan2.2 I2V生成5秒竖屏视频...")

    scripts_dir = str(config.SCRIPTS_PKG_DIR)
    sys.path.insert(0, scripts_dir)
    from comfyui_api import check_comfyui_running, submit_workflows_from_dir, wait_for_all_tasks

    comfyui_url = config.COMFYUI_API_URL

    if not comfyui_running:
        print("  ⏭ ComfyUI未运行，跳过自动生视频")
        print("  📋 手动操作步骤：")
        print("    1. 确保分镜图已准备好并放入 ComfyUI input/ 目录")
        print(f"    2. 导入工作流: {workflow_dir}/scene_XX_wan22_i2v.json")
        print("    3. 在LoadImage节点选择对应分镜图")
        print("    4. 点击Queue Prompt执行")
        print("    5. 每段5秒，建议每段多抽卡3-5条，选最优")
        print(f"    6. 预计耗时: ~3-6分钟/段（4090 FP16直出）")
        print("  💡 长视频策略：5秒+5秒+5秒，尾帧续写，交叉淡化拼接")
        return False

    try:
        if not check_comfyui_running(comfyui_url):
            print(f"  ✗ ComfyUI服务未运行 ({comfyui_url})")
            return False

        prompt_ids = submit_workflows_from_dir(workflow_dir, comfyui_url, pattern="*_wan22_i2v.json")
        if not prompt_ids:
            print("  ⚠ 未找到Wan2.2工作流文件")
            return False

        print(f"  ✓ 已提交 {len(prompt_ids)} 个Wan2.2任务")
        print("  💡 建议：每个分镜生成3-5条，筛选最优后再拼接")

        print("  ⏳ 等待Wan2.2生视频完成（5秒/段，预计3-6分钟/段）...")
        results = wait_for_all_tasks(prompt_ids, comfyui_url, poll_interval=10, timeout=3600)
        completed = sum(1 for v in results.values() if v.get("status") == "completed")
        print(f"  ✓ Wan2.2视频生成完成: {completed}/{len(prompt_ids)}")
        return True

    except Exception as e:
        logger.error(f"ComfyUI连接失败: {e}")
        return False


# ============ 步骤3：TTS配音先行 ============
def step5_generate_tts(script_path, output_dir):
    """步骤3：TTS配音先行——根据剧本生成配音，先出音频再出分镜"""
    print_step(3, 7, "TTS配音先行...")

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

    print_header("短剧制作Pipeline v5.2 - 租算力+SDXL+LoRA锁人+5秒分段版 (9:16)")
    print(f"  硬件: 云GPU RTX 4090 24GB (AutoDL/极智算)")
    print(f"  成本: ¥{cost_per_hour}/小时")
    print(f"  分辨率: SDXL 768x1344 → Wan2.2 832x480 → 可选upscale 1080P")
    print(f"  人物锁人: LoRA ({config.LORA_NAME}, 强度 {config.LORA_STRENGTH})")
    print(f"  流程: 剧本→TTS先行→SDXL生图(LoRA锁人)→筛选→Wan2.2生视频→续写→拼接→合成")
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

    # 步骤3：TTS配音先行
    tts_results = None
    if enable_tts:
        tts_results = step5_generate_tts(script_path, output_dir)
        # TODO: 根据TTS音频时长计算分镜张数

    # 步骤4：SDXL文生图（租算力+LoRA锁人）
    storyboard_images = step4_generate_images(script_path, output_dir, comfyui_running)

    # 步骤5：Wan2.2生视频（5秒/段）
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
    print(f"  分镜图: {len(storyboard_images)} 张 (SDXL + LoRA锁人)")
    print(f"  分辨率: SDXL 768x1344 → Wan2.2 832x480 → 可选upscale 1080P")
    print(f"  预估制作时间: {cost_info['time']['total_readable']}")
    print(f"  预估制作成本: {cost_info['cost']['total']}")
    print(f"  本次Pipeline耗时: {elapsed:.1f}秒")
    print(f"\n  💡 手动执行ComfyUI工作流:")
    if latest_wf:
        print(f"    SDXL: 运行 scripts/generate_images.py --script {script_path}")
        print(f"    Wan2.2 I2V: 导入 {latest_wf}/scene_XX_wan22_i2v.json")
        print(f"    尾帧续写: 使用 ComfyUI-WanVideoStartEndFrames 插件")
        print(f"    拼接: 多段5秒视频 + 交叉淡化(0.5s) → 15秒+ 成片")
    if not enable_tts:
        print(f"    TTS配音: 加 --tts 参数自动生成配音")
    print()


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="短剧制作Pipeline v5.0 — 配音先行版")
    parser.add_argument("--auto", action="store_true", help="全自动模式")
    parser.add_argument("--run-comfyui", action="store_true", help="调用ComfyUI API生视频（需ComfyUI服务运行中）")
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
        print_header(f"短剧制作成本估算 (云GPU RTX 4090, ¥{cost_per_hour}/小时)")
        print("\n| 集数 | 分镜 | 视频(抽卡3) | 含TTS | SDXL耗时 | Wan耗时 | 总耗时 | 总成本 | 每集成本 |")
        print("|:----:|:----:|:---------:|:-----:|--------:|-------:|--------|--------|---------:|")
        for n in [1, 5, 10, 30, 50, 100]:
            info = estimate_cost(num_episodes=n, include_tts=True)
            print(f"| {n} | {info['total_images']} | {info['total_videos']} | ✓ | {info['time']['sdxl']} | {info['time']['wan22']} | {info['time']['total_hours']} | {info['cost']['total']} | {info['cost']['total_per_episode']} |")
        print()
        print("💡 SDXL文生图: 768x1344, LoRA锁人, 每场3张, 约10-20秒/张")
        print("💡 Wan2.2 I2V: 5秒/段, 每段抽卡3条, 约3-6分钟/条")
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
短剧制作Pipeline v5.2 — 租算力+SDXL+LoRA锁人+5秒分段版
用法:
  python pipeline.py --auto                         全自动：抓热点→剧本→TTS先行
  python pipeline.py --auto --genre "霸总"          指定题材
  python pipeline.py --auto --run-comfyui           全自动+SDXL文生图+Wan2.2生视频
  python pipeline.py --auto --run-comfyui --tts     全自动+全套（TTS+字幕+合成）
  python pipeline.py --from-script <剧本.md>        从已有剧本开始
  python pipeline.py --cost-estimate                查看成本估算

完整8步流程（配音先行 + SDXL + LoRA锁人 + 图生视频）：
  1. 抓取热点 (酷乐API + 抖音热搜)
  2. 生成剧本 (含对白/旁白 + SDXL提示词 + LoRA锁人词)
  3. TTS配音先行 (先出音频，音频时长决定分镜张数和节奏)
  4. SDXL文生图 (768x1344竖屏, LoRA锁人, 每场3张抽卡, 租算力4090)
  5. 人工筛选分镜图 (或自动筛选)
  6. Wan2.2生视频 (5秒/段, FP16直出, 尾帧续写)
  7. 字幕生成 (SRT格式，基于TTS时长精确生成时间轴)
  8. FFmpeg拼接合成 (多段5秒 + 交叉淡化 → 15秒+成片)

v5.2 核心变化 (相比v5.1):
  - 新增SDXL文生图自动化 (scripts/generate_images.py)
  - LoRA锁人保证跨场人物一致性
  - IP-Adapter可选参考图锁脸
  - 流程从7步扩展为8步，SDXL自动生成替代手动准备
  - 成本模型包含SDXL文生图耗时和费用
    """)


if __name__ == "__main__":
    main()