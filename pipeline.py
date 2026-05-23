#!/usr/bin/env python3
"""
短剧制作一键Pipeline (Shortdrama Production Pipeline)

完整流程：
  1. 抓取热点 → 2. 生成剧本(含ComfyUI配置) → 3. 调用ComfyUI生图 → 4. 调用Wan2.2生视频 → 5. FFmpeg合成

使用方式：
  python pipeline.py --auto                    # 全自动：抓热点→生成剧本→生成ComfyUI配置
  python pipeline.py --auto --run-comfyui      # 全自动+调用ComfyUI（需ComfyUI服务运行中）
  python pipeline.py --from-script <script.md> # 从已有剧本生成ComfyUI工作流
  python pipeline.py --cost-estimate           # 仅计算成本估算

硬件环境：RTX 4080S 32GB RAM
成本：1.8元/小时 (AutoDL云算力)
分辨率：1080x1920 (9:16竖屏)
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ============ 配置 ============

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
TEMPLATE_DIR = os.path.join(PROJECT_DIR, "templates")
WORKFLOW_DIR = os.path.join(PROJECT_DIR, "workflows")

# 输出目录
DEFAULT_OUTPUT_DIR = r"D:\视频生产\reports\shortdrama"
DEFAULT_SCRIPT_DIR = os.path.join(DEFAULT_OUTPUT_DIR, "scripts")
DEFAULT_VIDEO_DIR = os.path.join(DEFAULT_OUTPUT_DIR, "videos")

# ComfyUI API配置
COMFYUI_API_URL = "http://127.0.0.1:8188"

# 成本参数（4080S 32G, 1.8元/小时）
COST_PER_HOUR = 1.8
SDXL_TIME_PER_IMAGE_S = 10       # 4080S上SDXL生成一张约10秒
WAN22_TIME_PER_VIDEO_S = 240     # 4080S上Wan2.2生成8秒视频约4分钟
FFMPEG_TIME_S = 120              # FFmpeg合成约2分钟


def print_header(title):
    """打印步骤标题"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def print_step(step_num, total_steps, description):
    """打印步骤信息"""
    print(f"\n[{step_num}/{total_steps}] {description}")


def estimate_cost(num_episodes=1, scenes_per_episode=5, angles_per_scene=3):
    """
    计算制作成本估算
    
    参数：
        num_episodes: 集数
        scenes_per_episode: 每集场数
        angles_per_scene: 每场机位数
    
    返回：
        成本估算字典
    """
    total_images = num_episodes * scenes_per_episode * angles_per_scene
    total_videos = total_images
    
    sdxl_time = total_images * SDXL_TIME_PER_IMAGE_S
    wan22_time = total_videos * WAN22_TIME_PER_VIDEO_S
    ffmpeg_time = num_episodes * FFMPEG_TIME_S
    total_time = sdxl_time + wan22_time + ffmpeg_time
    
    sdxl_cost = (sdxl_time / 3600) * COST_PER_HOUR
    wan22_cost = (wan22_time / 3600) * COST_PER_HOUR
    ffmpeg_cost = (ffmpeg_time / 3600) * COST_PER_HOUR
    total_cost = sdxl_cost + wan22_cost + ffmpeg_cost
    
    return {
        "num_episodes": num_episodes,
        "total_images": total_images,
        "total_videos": total_videos,
        "time": {
            "sdxl": f"{sdxl_time//60}分{sdxl_time%60}秒",
            "wan22": f"{wan22_time//60}分{wan22_time%60}秒",
            "ffmpeg": f"{ffmpeg_time//60}分{ffmpeg_time%60}秒",
            "total_seconds": total_time,
            "total_readable": f"{total_time//60}分{total_time%60}秒",
            "total_hours": f"{total_time/3600:.1f}小时",
        },
        "cost": {
            "sdxl": f"¥{sdxl_cost:.3f}",
            "wan22": f"¥{wan22_cost:.2f}",
            "ffmpeg": f"¥{ffmpeg_cost:.3f}",
            "total": f"¥{total_cost:.2f}",
            "total_per_episode": f"¥{total_cost/max(num_episodes,1):.2f}",
        },
        "hardware": "RTX 4080S 32GB RAM",
        "rate": f"¥{COST_PER_HOUR}/小时",
    }


def step1_fetch_hotspot(output_dir):
    """步骤1：抓取短剧热点"""
    print_step(1, 5, "抓取短剧热点数据...")
    
    # 导入fetch_hotspot模块
    sys.path.insert(0, SCRIPT_DIR)
    from fetch_hotspot import fetch_shortdrama_rank, fetch_douyin_hot, generate_genre_stats
    
    rank_data = fetch_shortdrama_rank()
    if not rank_data:
        print("[ERROR] 未能获取热点数据")
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


def step2_generate_script(rank_data, output_dir, genre=None, comfyui_mode=True):
    """步骤2：生成剧本（含ComfyUI配置）"""
    print_step(2, 5, "生成仿制剧本（ComfyUI可执行版）...")
    
    sys.path.insert(0, os.path.join(SCRIPT_DIR, "scripts") if os.path.exists(os.path.join(SCRIPT_DIR, "scripts")) else SCRIPT_DIR)
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
    if comfyui_mode:
        wf_dir = os.path.join(script_output, "workflows")
        print(f"  ✓ ComfyUI工作流: {wf_dir}")
    
    return filepath, title, script_genre


def step3_generate_images(workflow_dir, comfyui_running=False):
    """步骤3：SDXL生成分镜图"""
    print_step(3, 5, "SDXL生成1080P竖屏分镜图...")
    
    if not comfyui_running:
        print("  ⏭ ComfyUI未运行，跳过自动生图")
        print("  📋 手动操作步骤：")
        print("    1. 启动ComfyUI (python main.py --listen)")
        print(f"    2. 导入工作流: {workflow_dir}/scene_XX_sdxl.json")
        print("    3. 点击Queue Prompt执行")
        print(f"    4. 预计耗时: ~2-3分钟（15张图）")
        return False
    
    # 调用ComfyUI API
    try:
        import urllib.request
        # 检查ComfyUI是否在线
        req = urllib.request.Request(f"{COMFYUI_API_URL}/system_stats")
        with urllib.request.urlopen(req, timeout=5) as resp:
            print("  ✓ ComfyUI服务已连接")
        
        # 遍历工作流文件提交任务
        sdxl_files = sorted([f for f in os.listdir(workflow_dir) if f.endswith("_sdxl.json")])
        for wf_file in sdxl_files:
            wf_path = os.path.join(workflow_dir, wf_file)
            with open(wf_path, "r", encoding="utf-8") as f:
                workflow = json.load(f)
            
            # 提交到ComfyUI
            prompt_data = json.dumps({"prompt": workflow}).encode()
            req = urllib.request.Request(
                f"{COMFYUI_API_URL}/prompt",
                data=prompt_data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                print(f"  ✓ 已提交: {wf_file} (prompt_id: {result.get('prompt_id', '?')[:8]})")
        
        print(f"  ✓ 共提交 {len(sdxl_files)} 个SDXL任务")
        return True
        
    except Exception as e:
        print(f"  ✗ ComfyUI连接失败: {e}")
        print("  📋 请手动导入工作流执行")
        return False


def step4_generate_videos(workflow_dir, comfyui_running=False):
    """步骤4：Wan2.2生成8秒视频"""
    print_step(4, 5, "Wan2.2 I2V生成8秒竖屏视频...")
    
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
        import urllib.request
        wan22_files = sorted([f for f in os.listdir(workflow_dir) if f.endswith("_wan22_i2v.json")])
        for wf_file in wan22_files:
            wf_path = os.path.join(workflow_dir, wf_file)
            with open(wf_path, "r", encoding="utf-8") as f:
                workflow = json.load(f)
            
            prompt_data = json.dumps({"prompt": workflow}).encode()
            req = urllib.request.Request(
                f"{COMFYUI_API_URL}/prompt",
                data=prompt_data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                print(f"  ✓ 已提交: {wf_file} (prompt_id: {result.get('prompt_id', '?')[:8]})")
        
        print(f"  ✓ 共提交 {len(wan22_files)} 个Wan2.2任务")
        return True
        
    except Exception as e:
        print(f"  ✗ ComfyUI连接失败: {e}")
        return False


def step5_compose_video(video_dir, output_dir):
    """步骤5：FFmpeg合成最终视频"""
    print_step(5, 5, "FFmpeg合成最终视频...")
    
    # 检查FFmpeg
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        if result.returncode != 0:
            raise FileNotFoundError
        print("  ✓ FFmpeg可用")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("  ✗ FFmpeg未找到，请安装后重试")
        return False
    
    # 查找视频文件
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
    
    output_file = os.path.join(output_dir, f"shortdrama_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")
    
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", concat_file,
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-c:a", "aac", "-b:a", "128k",
        output_file
    ]
    
    print(f"  合成 {len(video_files)} 个视频片段...")
    result = subprocess.run(cmd, capture_output=True, timeout=300)
    
    if result.returncode == 0:
        print(f"  ✓ 合成完成: {output_file}")
        return True
    else:
        print(f"  ✗ 合成失败: {result.stderr.decode()[:200]}")
        return False


def run_pipeline(genre=None, comfyui_running=False):
    """执行完整Pipeline"""
    start_time = time.time()
    
    print_header("短剧制作Pipeline - 1080P竖屏 (9:16)")
    print(f"  硬件: RTX 4080S 32GB RAM")
    print(f"  成本: ¥{COST_PER_HOUR}/小时")
    print(f"  分辨率: 1080x1920")
    print(f"  ComfyUI: {'在线' if comfyui_running else '离线（手动模式）'}")
    
    # 确保输出目录存在
    os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)
    os.makedirs(DEFAULT_SCRIPT_DIR, exist_ok=True)
    os.makedirs(DEFAULT_VIDEO_DIR, exist_ok=True)
    
    # 步骤1：抓取热点
    rank_data = step1_fetch_hotspot(DEFAULT_OUTPUT_DIR)
    if not rank_data:
        print("\n❌ Pipeline失败：无法获取热点数据")
        return
    
    # 步骤2：生成剧本
    script_path, title, script_genre = step2_generate_script(
        rank_data, DEFAULT_OUTPUT_DIR, genre=genre, comfyui_mode=True
    )
    
    # 步骤3：SDXL生图
    # 找到最新生成的工作流目录
    wf_base = os.path.join(DEFAULT_SCRIPT_DIR, "workflows")
    latest_wf = None
    if os.path.exists(wf_base):
        wf_dirs = sorted([d for d in os.listdir(wf_base) if os.path.isdir(os.path.join(wf_base, d))])
        if wf_dirs:
            latest_wf = os.path.join(wf_base, wf_dirs[-1])
    
    if latest_wf:
        step3_generate_images(latest_wf, comfyui_running)
        step4_generate_videos(latest_wf, comfyui_running)
    else:
        print("\n  ⏭ 未找到ComfyUI工作流目录，跳过步骤3-4")
    
    # 步骤5：合成视频
    step5_compose_video(DEFAULT_VIDEO_DIR, DEFAULT_OUTPUT_DIR)
    
    # 成本汇总
    elapsed = time.time() - start_time
    cost_info = estimate_cost(num_episodes=1)
    
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
    print()


def main():
    """主入口"""
    args = sys.argv[1:]
    
    if "--cost-estimate" in args:
        # 成本估算模式
        print_header("短剧制作成本估算 (RTX 4080S, ¥1.8/小时)")
        print("\n| 集数 | 图片数 | 视频数 | 预估时间 | 预估成本 | 每集成本 |")
        print("|:----:|:------:|:------:|----------|---------:|---------:|")
        for n in [1, 5, 10, 30, 50, 100]:
            info = estimate_cost(num_episodes=n)
            print(f"| {n} | {info['total_images']} | {info['total_videos']} | {info['time']['total_hours']} | {info['cost']['total']} | {info['cost']['total_per_episode']} |")
        print()
        return
    
    if "--auto" in args:
        # 全自动模式
        comfyui_running = "--run-comfyui" in args
        genre = None
        for i, arg in enumerate(args):
            if arg == "--genre" and i + 1 < len(args):
                genre = args[i + 1]
        run_pipeline(genre=genre, comfyui_running=comfyui_running)
        return
    
    # 默认：显示帮助
    print("""
短剧制作Pipeline v2.0 - 1080P竖屏 (9:16)

用法:
  python pipeline.py --auto                    全自动：抓热点→生成剧本→ComfyUI配置
  python pipeline.py --auto --genre "霸总"     指定题材
  python pipeline.py --auto --run-comfyui      全自动+调用ComfyUI API
  python pipeline.py --cost-estimate           查看成本估算

制作流程:
  1. 抓取热点 (酷乐API + 抖音热搜)
  2. 生成剧本 (含SDXL/Wan2.2提示词)
  3. SDXL生图 (1024x1820 → 1080x1920, ~8-12秒/张)
  4. Wan2.2生视频 (8秒/段, ~3-5分钟/段)
  5. FFmpeg合成 (字幕+配音)

硬件: RTX 4080S 32GB RAM
成本: ¥1.8/小时 → 约¥1.9/集
分辨率: 1080x1920 (9:16竖屏)
    """)


if __name__ == "__main__":
    main()
