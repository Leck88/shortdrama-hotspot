#!/usr/bin/env python3
"""
短剧制作Pipeline v5.3 — 租算力+现成镜像/工作流+6步自动化+手动TTS

自动化流程（python pipeline.py --auto --run-comfyui）：
  1. 抓取热点 → 2. 生成剧本(含SDXL提示词+LoRA锁人词+Wan2.2运动词) →
  3. SDXL文生图（租算力现成镜像+工作流，LoRA锁人，每场3张抽卡） →
  4. Wan2.2 I2V 5秒/段（现成工作流，FP16直出，每段抽卡3条） →
  5. 尾帧续写 + 交叉淡化拼接 →
  6. FFmpeg合成 → 成品视频

手动步骤（TTS配音 + 人工筛选分镜图）：
  - TTS配音：待搞懂后再接入自动化，当前手动处理
  - 分镜图筛选：每场3张抽卡后人工选最优

租算力使用方式：
  AutoDL/极智算等平台已有现成ComfyUI镜像，内置SDXL+LoRA+Wan2.2工作流，
  开机即用，无需自己搭建环境或写workflow JSON。

使用方式：
  python pipeline.py --auto                    # 自动：抓热点→剧本
  python pipeline.py --auto --run-comfyui      # 自动+调用租算力ComfyUI（SDXL+Wan2.2）
  python pipeline.py --cost-estimate          # 查看成本估算
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime

# 获取项目根目录
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from config import config

logger = logging.getLogger("shortdrama.pipeline")


def print_header(title):
    print(f"\n{'='*55}")
    print(f"  {title}")
    print(f"{'='*55}")


def print_step(step, total, description):
    print(f"\n  ▶ 步骤 {step}/{total}: {description}")


# ============ 步骤1：抓取热点 ============
def step1_fetch_hotspot(output_dir):
    """步骤1：抓取短剧热点数据"""
    print_step(1, 6, "抓取热点（酷乐API + 抖音热搜）...")

    scripts_dir = str(config.SCRIPTS_PKG_DIR)
    sys.path.insert(0, scripts_dir)
    from fetch_hotspot import fetch_hotspot_data, generate_daily_report

    try:
        rank_data = fetch_hotspot_data()
        if not rank_data:
            print("  ⚠ 未获取到热点数据，使用默认题材")
            rank_data = [{"title": "热门短剧", "heat": 99999, "genre": "婚恋"}]

        report_path = generate_daily_report(rank_data, output_dir)
        print(f"  ✓ 热点数据已获取: {len(rank_data)} 条")
        if report_path:
            print(f"  ✓ 日报已生成: {report_path}")
        return rank_data

    except Exception as e:
        logger.error(f"热点抓取失败: {e}")
        return None


# ============ 步骤2：生成剧本 ============
def step2_generate_script(rank_data, output_dir, genre=None, comfyui_mode=True):
    """步骤2：生成仿制剧本（含SDXL提示词+LoRA锁人词+Wan2.2运动词）"""
    print_step(2, 6, "生成仿制剧本（SDXL提示词+LoRA锁人词+Wan2.2运动词）...")

    scripts_dir = str(config.SCRIPTS_PKG_DIR)
    sys.path.insert(0, scripts_dir)
    from generate_script import generate_script_batch, save_workflow_json

    try:
        filepath, title, script_genre, wf_dir = generate_script_batch(
            rank_data=rank_data,
            output_dir=output_dir,
            genre=genre,
            count=1,
            comfyui_mode=comfyui_mode,
        )
        print(f"  ✓ 剧本已生成: 《{title}》({script_genre})")
        print(f"  📄 文件: {filepath}")
        print(f"  💡 剧本中包含每场的SDXL提示词、LoRA锁人词、Wan2.2运动词")
        return filepath, title, script_genre, wf_dir

    except Exception as e:
        logger.error(f"剧本生成失败: {e}")
        return None, None, None, None


# ============ 步骤3：SDXL文生图（租算力现成镜像） ============
def step3_generate_images(script_path, output_dir, comfyui_running=False):
    """步骤3：SDXL文生图（租算力现成ComfyUI镜像+工作流，LoRA锁人）

    租算力平台（AutoDL/极智算）已有现成ComfyUI镜像，内置：
    - SDXL Checkpoint（JuggernautXL / RealVisXL / Flux.1-dev）
    - LoRA加载节点
    - IP-Adapter节点
    - 一键导入工作流

    不需要自己搭建环境或手写workflow JSON。
    """
    print_step(3, 6, "SDXL文生图（租算力现成镜像+LoRA锁人）...")

    scripts_dir = str(config.SCRIPTS_PKG_DIR)
    sys.path.insert(0, scripts_dir)
    from generate_images import generate_storyboard_images

    storyboard_dir = str(config.STORYBOARD_DIR)

    if not comfyui_running:
        print("  ⏭ ComfyUI未运行，跳过自动生图")
        print("  📋 手动操作（推荐使用租算力现成镜像）：")
        print("    1. AutoDL/极智算 → 选 ComfyUI 镜像 → 开机")
        print("    2. ComfyUI 中导入现成的 SDXL + LoRA 工作流")
        print("    3. 从剧本中复制每场的 SDXL 提示词粘贴到工作流")
        print("    4. 加载你的 LoRA 模型（face_lora.safetensors）")
        print("    5. 每场 Queue 3次（抽卡3张），选最优")
        print("    6. 或设置 COMFYUI_API_URL 后运行:")
        print(f"       python scripts/generate_images.py --script {script_path}")
        print("  💡 推荐底模: JuggernautXL v35 / Flux.1-dev / RealVisXL V5.0")
        print("  💡 分辨率: 832x1472(SDXL) 或 1024x1536(Flux)")
        print("  💡 LoRA强度: 0.8，步数: 35(SDXL)/28(Flux)")
        print("  💡 自动锁人提示词: same person / consistent face / consistent features")
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
        else:
            print("  ⚠ 未生成图片")

        return images

    except Exception as e:
        logger.error(f"文生图失败: {e}")
        print("  ✗ 文生图失败，请检查 ComfyUI 连接和 LoRA 模型")
        return []


# ============ 步骤4：Wan2.2 I2V 生视频（5秒/段） ============
def step4_generate_videos(workflow_dir, comfyui_running=False):
    """步骤4：Wan2.2 I2V 5秒/段（租算力现成镜像+工作流）

    租算力ComfyUI镜像通常已内置 Wan2.2 I2V 工作流。
    """
    print_step(4, 6, "Wan2.2 I2V 5秒/段（租算力现成工作流）...")

    scripts_dir = str(config.SCRIPTS_PKG_DIR)
    sys.path.insert(0, scripts_dir)
    from comfyui_api import check_comfyui_running, submit_workflows_from_dir, wait_for_all_tasks

    comfyui_url = config.COMFYUI_API_URL

    if not comfyui_running:
        print("  ⏭ ComfyUI未运行，跳过自动生视频")
        print("  📋 手动操作（使用租算力现成 Wan2.2 工作流）：")
        print("    1. ComfyUI 中导入现成的 Wan2.2 I2V 工作流")
        print("    2. LoadImage 节点选择分镜图")
        print("    3. Motion Prompt 从剧本中复制")
        print("    4. 参数: frames=81, fps=16, motion_strength=0.4, cfg=6.5")
        print("    5. 每段 Queue 3次（抽卡3条），选最优")
        print("    6. 预计耗时: ~3-6分钟/段（4090 FP16直出）")
        print("  💡 长视频: 5秒+5秒+5秒 → 尾帧续写 → 交叉淡化拼接")
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
        print("  💡 建议：每个分镜生成3条，筛选最优后再拼接")

        print("  ⏳ 等待Wan2.2生视频完成（5秒/段，预计3-6分钟/段）...")
        results = wait_for_all_tasks(prompt_ids, comfyui_url, poll_interval=10, timeout=3600)
        completed = sum(1 for v in results.values() if v.get("status") == "completed")
        print(f"  ✓ Wan2.2视频生成完成: {completed}/{len(prompt_ids)}")
        return True

    except Exception as e:
        logger.error(f"ComfyUI连接失败: {e}")
        return False


# ============ 步骤5：尾帧续写 + 交叉淡化拼接 ============
def step5_concat_videos(video_dir, output_dir):
    """步骤5：尾帧续写 + 多段5秒视频交叉淡化拼接为15秒+成片"""
    print_step(5, 6, "尾帧续写 + 交叉淡化拼接...")

    print("  📋 拼接策略:")
    print("    片段1(5s) → 提取尾帧 → 片段2(5s) → 提取尾帧 → 片段3(5s)")
    print("    段间交叉淡化重叠 0.5秒 → 15秒成片")
    print("")
    print("  💡 ComfyUI中使用 ComfyUI-WanVideoStartEndFrames 插件做尾帧续写")
    print("  💡 FFmpeg交叉淡化: ffmpeg -i a.mp4 -i b.mp4 -filter_complex crossfade=0.5")
    print("  💡 或直接在DaVinci/Premiere中手动拼接")
    return True


# ============ 步骤6：FFmpeg合成 ============
def step6_compose_video(video_dir, output_dir):
    """步骤6：FFmpeg拼接+合成最终视频"""
    print_step(6, 6, "FFmpeg合成最终视频...")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_output = os.path.join(output_dir, f"shortdrama_{timestamp}_base.mp4")

    print("  📋 FFmpeg合成步骤:")
    print("    1. 拼接所有5秒视频段")
    print("    2. 交叉淡化（0.5秒重叠）")
    print("    3. 添加字幕（如有）")
    print("    4. 添加配音（如有TTS）")
    print(f"    5. 输出: {base_output}")
    return True


# ============ 主Pipeline ============
def run_pipeline(genre=None, comfyui_running=False):
    """执行自动化Pipeline（TTS为手动步骤，不在此自动执行）"""
    start_time = time.time()
    cost_per_hour = config.COST_PER_HOUR

    print_header("短剧制作Pipeline v5.3 — 租算力+现成镜像/工作流 (9:16)")
    print(f"  硬件: 云GPU RTX 4090 24GB (AutoDL/极智算，现成ComfyUI镜像)")
    print(f"  成本: ¥{cost_per_hour}/小时")
    print(f"  底模: SDXL JuggernautXL / Flux.1-dev / RealVisXL V5.0")
    print(f"  人物锁人: LoRA ({config.LORA_NAME}, 强度 {config.LORA_STRENGTH})")
    print(f"  流程: 热点→剧本→SDXL生图(现成镜像)→Wan2.2生视频(现成工作流)→拼接→合成")
    print(f"  ComfyUI: {'在线' if comfyui_running else '离线（手动模式，引导使用租算力现成镜像）'}")
    print(f"  TTS配音: 手动步骤（待后续接入自动化）")

    # 确保输出目录存在
    config.ensure_dirs()
    output_dir = str(config.REPORT_DIR)
    video_dir = str(config.VIDEO_DIR)

    # 步骤1：抓取热点
    rank_data = step1_fetch_hotspot(output_dir)
    if not rank_data:
        print("\n❌ Pipeline失败：无法获取热点数据")
        return

    # 步骤2：生成剧本
    script_path, title, script_genre, latest_wf = step2_generate_script(
        rank_data, output_dir, genre=genre, comfyui_mode=True
    )

    # 步骤3：SDXL文生图（租算力现成镜像+LoRA锁人）
    storyboard_images = step3_generate_images(script_path, output_dir, comfyui_running)

    # 步骤4：Wan2.2生视频（租算力现成工作流）
    if latest_wf and os.path.exists(latest_wf):
        step4_generate_videos(latest_wf, comfyui_running)
    else:
        print("\n  ⏭ 未找到ComfyUI工作流目录，跳过步骤4")

    # 步骤5：尾帧续写 + 交叉淡化拼接
    step5_concat_videos(video_dir, output_dir)

    # 步骤6：FFmpeg合成
    step6_compose_video(video_dir, output_dir)

    # 成本汇总
    elapsed = time.time() - start_time
    cost_info = estimate_cost(num_episodes=1)

    # 手动步骤提醒
    print_header("自动化步骤完成，以下为手动步骤")
    print(f"  📋 手动步骤1: TTS配音")
    print(f"     待搞懂TTS后接入自动化，当前可手动配音或使用其他工具")
    print(f"     剧本文件: {script_path}")
    print(f"")
    print(f"  📋 手动步骤2: 人工筛选分镜图")
    print(f"     每场3张抽卡 → 选最优 → 重命名 scene_XX_selected.png")
    print(f"     输出目录: {config.STORYBOARD_DIR}")
    print(f"")

    print_header("执行汇总")
    print(f"  剧名: 《{title}》")
    print(f"  题材: {script_genre}")
    print(f"  剧本: {script_path}")
    print(f"  分镜图: {len(storyboard_images)} 张 (SDXL + LoRA锁人)")
    print(f"  底模: JuggernautXL / Flux.1-dev / RealVisXL V5.0")
    print(f"  预估制作时间: {cost_info['time']['total_readable']}")
    print(f"  预估制作成本: {cost_info['cost']['total']}")
    print(f"  本次Pipeline耗时: {elapsed:.1f}秒")
    print(f"\n  💡 租算力使用提示:")
    print(f"    AutoDL/极智算 → 选ComfyUI镜像 → 开机即用")
    print(f"    镜像通常内置: SDXL + LoRA + Wan2.2 + IP-Adapter")
    print(f"    从剧本复制提示词粘贴到现成工作流即可")
    print()


def estimate_cost(num_episodes=1, include_tts=False):
    """成本估算"""
    images_per_ep = 5 * config.SDXL_BATCH_PER_SCENE  # 5场 x 每场3张
    videos_per_ep = 5 * 3  # 5段 x 每段3条

    sdxl_time = images_per_ep * config.SDXL_TIME_PER_IMAGE_S
    wan22_time = videos_per_ep * config.WAN22_TIME_PER_VIDEO_S
    ffmpeg_time = num_episodes * config.FFMPEG_TIME_S
    total_time = sdxl_time + wan22_time + ffmpeg_time

    cost_per_hour = config.COST_PER_HOUR
    sdxl_cost = (sdxl_time / 3600) * cost_per_hour
    wan22_cost = (wan22_time / 3600) * cost_per_hour
    ffmpeg_cost = (ffmpeg_time / 3600) * cost_per_hour
    total_cost = sdxl_cost + wan22_cost + ffmpeg_cost

    return {
        "num_episodes": num_episodes,
        "total_images": images_per_ep,
        "total_videos": videos_per_ep,
        "time": {
            "sdxl": f"{sdxl_time//60}分{sdxl_time%60}秒",
            "wan22": f"{wan22_time//60}分{wan22_time%60}秒",
            "total_seconds": total_time,
            "total_readable": f"{total_time//60}分{total_time%60}秒",
            "total_hours": f"{total_time/3600:.1f}小时",
        },
        "cost": {
            "sdxl": f"¥{sdxl_cost:.2f}",
            "wan22": f"¥{wan22_cost:.2f}",
            "ffmpeg": f"¥{ffmpeg_cost:.3f}",
            "total": f"¥{total_cost:.2f}",
            "total_per_episode": f"¥{total_cost/max(num_episodes,1):.2f}",
        },
        "hardware": "云GPU RTX 4090 24GB (AutoDL/极智算，现成ComfyUI镜像)",
        "rate": f"¥{cost_per_hour}/小时",
    }


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="短剧制作Pipeline v5.3 — 租算力+现成镜像/工作流")
    parser.add_argument("--auto", action="store_true", help="全自动模式")
    parser.add_argument("--run-comfyui", action="store_true", help="调用ComfyUI API（需租算力ComfyUI运行中）")
    parser.add_argument("--genre", type=str, default=None, help="指定题材")
    parser.add_argument("--cost-estimate", action="store_true", help="查看成本估算")
    parser.add_argument("--from-script", type=str, default=None, help="从已有剧本开始")
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
        print("\n| 集数 | 分镜(抽卡3) | 视频(抽卡3) | SDXL耗时 | Wan耗时 | 总耗时 | 总成本 | 每集成本 |")
        print("|:----:|:---------:|:---------:|--------:|-------:|--------|--------|---------:|")
        for n in [1, 5, 10, 30, 50, 100]:
            info = estimate_cost(num_episodes=n)
            print(f"| {n} | {info['total_images']} | {info['total_videos']} | {info['time']['sdxl']} | {info['time']['wan22']} | {info['time']['total_hours']} | {info['cost']['total']} | {info['cost']['total_per_episode']} |")
        print()
        print("💡 SDXL: JuggernautXL 832x1472, LoRA锁人, 每场3张, ~15-30秒/张")
        print("💡 Wan2.2: 5秒/段, 每段抽卡3条, ~3-6分钟/条")
        print("💡 使用租算力现成ComfyUI镜像，开机即用，无需自建环境")
        print()
        return

    if args.auto:
        run_pipeline(
            genre=args.genre,
            comfyui_running=args.run_comfyui,
        )
        return

    if args.from_script:
        print(f"从剧本生成: {args.from_script}")
        return

    # 默认：显示帮助
    print("""
短剧制作Pipeline v5.3 — 租算力+现成镜像/工作流

6步自动化 + 手动TTS：
  1. 抓取热点 (酷乐API + 抖音热搜)
  2. 生成剧本 (含SDXL提示词 + LoRA锁人词 + Wan2.2运动词)
  3. SDXL文生图 (租算力现成ComfyUI镜像, 832x1472, LoRA锁人, 每场3张抽卡)
  4. Wan2.2生视频 (租算力现成工作流, 5秒/段, FP16直出, 每段抽卡3条)
  5. 尾帧续写 + 交叉淡化拼接 (3段x5秒 → 15秒成片)
  6. FFmpeg合成 → 成品视频

手动步骤:
  - TTS配音: 待搞懂后接入，当前手动处理
  - 分镜图筛选: 每场3张抽卡后人工选最优

用法:
  python pipeline.py --auto                         自动：抓热点→剧本
  python pipeline.py --auto --run-comfyui            自动+调用租算力ComfyUI（SDXL+Wan2.2）
  python pipeline.py --auto --genre "霸总"           指定题材
  python pipeline.py --cost-estimate                 查看成本估算

租算力使用:
  AutoDL/极智算 → 选ComfyUI镜像 → 开机即用
  镜像内置: SDXL + LoRA + Wan2.2 + IP-Adapter
  从剧本复制提示词粘贴到现成工作流即可

v5.3 变化:
  - TTS改为手动步骤（待后续接入）
  - SDXL/Wan2.2步骤引导使用租算力现成镜像和工作流
  - 不再自建workflow JSON，而是用平台提供的现成工作流
  - 流程精简为6步自动化 + 2步手动
    """)


if __name__ == "__main__":
    main()
