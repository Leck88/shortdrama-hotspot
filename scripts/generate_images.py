"""
文生图自动化脚本（租算力版）

通过 ComfyUI API 调用 SDXL/Flux 生成短剧分镜图。
核心功能：
  - 根据剧本自动生成分镜图（每场3-5张，筛选最优）
  - 支持 LoRA 锁人（人物一致性）
  - 支持 IP-Adapter 参考图锁脸
  - 9:16 竖屏输出（768x1344）
  - 租算力跑（通过 COMFYUI_API_URL 指向云端 ComfyUI）

使用方式：
  # 独立使用
  python scripts/generate_images.py --workflow-dir ./output/scripts/workflows/xxx

  # 通过 pipeline.py 调用
  python pipeline.py --auto --run-comfyui
"""

import json
import os
import sys
import time
import logging
import argparse
from pathlib import Path

# 获取项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import config

logger = logging.getLogger("generate_images")

# ============ 默认参数 ============

# SDXL 文生图默认参数（4090 FP16）
DEFAULT_SDXL_PARAMS = {
    "width": 768,
    "height": 1344,
    "cfg_scale": 6.0,
    "steps": 25,
    "sampler": "euler_ancestral",
    "scheduler": "normal",
    "checkpoint": "sd_xl_base_1.0.safetensors",
    "seed": -1,
}

# LoRA 锁人参数
DEFAULT_LORA_PARAMS = {
    "lora_name": "face_lora.safetensors",   # LoRA 模型文件名（放在 ComfyUI/models/loras/）
    "strength_model": 0.8,                   # 模型强度（0.5-1.0，越高越像）
    "strength_clip": 0.8,                    # CLIP 强度
}

# IP-Adapter 锁脸参数（LoRA 的替代方案）
DEFAULT_IPADAPTER_PARAMS = {
    "ipadapter_name": "ip-adapter_sdxl_plus.safetensors",
    "clip_vision_name": "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors",
    "strength": 0.7,
    "start_at": 0.0,
    "end_at": 1.0,
    "reference_image": "",  # 参考人脸图片路径
}

# 每场抽卡数量
DEFAULT_BATCH_PER_SCENE = 3


def build_sdxl_workflow(positive_prompt, negative_prompt, output_path="",
                        lora_params=None, ipadapter_params=None,
                        sdxl_params=None, scene_id=1):
    """
    构建 ComfyUI 可执行的 SDXL 文生图工作流 JSON

    参数：
        positive_prompt:     正向提示词
        negative_prompt:     反向提示词
        output_path:         输出图片文件名前缀
        lora_params:         LoRA 参数字典（人物锁人）
        ipadapter_params:    IP-Adapter 参数字典（参考图锁脸）
        sdxl_params:         SDXL 参数字典
        scene_id:            场次编号

    返回：
        ComfyUI workflow dict（可直接 POST /prompt）
    """
    params = {**DEFAULT_SDXL_PARAMS, **(sdxl_params or {})}

    # 节点ID规划
    node_id = {
        "checkpoint": "4",
        "lora": "10",
        "clip_text_pos": "6",
        "clip_text_neg": "7",
        "empty_latent": "5",
        "ksampler": "3",
        "vae_decode": "8",
        "save_image": "9",
        "ipadapter": "11",
    }

    workflow = {
        node_id["checkpoint"]: {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": params["checkpoint"]
            }
        },
    }

    # LoRA 节点（人物锁人）
    if lora_params:
        lora = {**DEFAULT_LORA_PARAMS, **lora_params}
        workflow[node_id["lora"]] = {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": lora["lora_name"],
                "strength_model": lora["strength_model"],
                "strength_clip": lora["strength_clip"],
                "model": [node_id["checkpoint"], 0],
                "clip": [node_id["checkpoint"], 1],
            }
        }
        model_src = node_id["lora"]
        clip_src = node_id["lora"]
    else:
        model_src = node_id["checkpoint"]
        clip_src = node_id["checkpoint"]

    # CLIP 正向/反向提示词
    workflow[node_id["clip_text_pos"]] = {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": positive_prompt,
            "clip": [clip_src, 0],
        }
    }
    workflow[node_id["clip_text_neg"]] = {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": negative_prompt,
            "clip": [clip_src, 0],
        }
    }

    # 空白潜空间
    workflow[node_id["empty_latent"]] = {
        "class_type": "EmptyLatentImage",
        "inputs": {
            "width": params["width"],
            "height": params["height"],
            "batch_size": 1,
        }
    }

    # IP-Adapter（参考图锁脸，可选）
    if ipadapter_params:
        ipa = {**DEFAULT_IPADAPTER_PARAMS, **ipadapter_params}
        workflow[node_id["ipadapter"]] = {
            "class_type": "IPAdapterApply",
            "inputs": {
                "ipadapter_name": ipa["ipadapter_name"],
                "clip_vision_name": ipa["clip_vision_name"],
                "strength": ipa["strength"],
                "start_at": ipa["start_at"],
                "end_at": ipa["end_at"],
                "model": [model_src, 0],
                "image": ipa.get("reference_image", ""),
            }
        }
        model_for_ksampler = node_id["ipadapter"]
    else:
        model_for_ksampler = model_src

    # KSampler
    workflow[node_id["ksampler"]] = {
        "class_type": "KSampler",
        "inputs": {
            "seed": params["seed"],
            "steps": params["steps"],
            "cfg": params["cfg_scale"],
            "sampler_name": params["sampler"],
            "scheduler": params["scheduler"],
            "denoise": 1.0,
            "model": [model_for_ksampler, 0],
            "positive": [node_id["clip_text_pos"], 0],
            "negative": [node_id["clip_text_neg"], 0],
            "latent_image": [node_id["empty_latent"], 0],
        }
    }

    # VAE 解码
    workflow[node_id["vae_decode"]] = {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": [node_id["ksampler"], 0],
            "vae": [model_src, 2],
        }
    }

    # 保存图片
    prefix = output_path or f"scene_{scene_id:02d}_storyboard"
    workflow[node_id["save_image"]] = {
        "class_type": "SaveImage",
        "inputs": {
            "filename_prefix": prefix,
            "images": [node_id["vae_decode"], 0],
        }
    }

    return workflow


def extract_sdxl_prompts_from_script(script_path):
    """
    从剧本 Markdown 中提取每场的 SDXL 提示词

    参数：
        script_path: 剧本 .md 文件路径

    返回：
        list[dict]: [{"scene_id": int, "name": str, "positive_prompt": str, "negative_prompt": str}]
    """
    scenes = []
    current_scene_id = None

    with open(script_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for line in lines:
        line = line.strip()

        # 检测场次标题：### 第X场 - 场名
        if line.startswith("### 第") and "场" in line:
            try:
                parts = line.replace("### 第", "").replace("场", "").split("-", 1)
                current_scene_id = int(parts[0].strip())
                scene_name = parts[1].strip() if len(parts) > 1 else f"第{current_scene_id}场"
                scenes.append({
                    "scene_id": current_scene_id,
                    "name": scene_name,
                    "positive_prompt": "",
                    "negative_prompt": "",
                })
            except (ValueError, IndexError):
                continue

        # 提取正向提示词
        if current_scene_id and "正向提示词:" in line:
            # 收集后续行直到遇到空行或新的标记
            idx = lines.index(line) if line in lines else -1
            prompt_lines = []
            if idx >= 0:
                # 跳过 "正向提示词:" 这一行
                for j in range(idx + 1, len(lines)):
                    next_line = lines[j].strip()
                    if not next_line or next_line.startswith("**") or next_line.startswith("反向"):
                        break
                    prompt_lines.append(next_line)
            if scenes:
                scenes[-1]["positive_prompt"] = " ".join(prompt_lines)

        # 提取反向提示词
        if current_scene_id and "反向提示词:" in line:
            idx = lines.index(line) if line in lines else -1
            prompt_lines = []
            if idx >= 0:
                for j in range(idx + 1, len(lines)):
                    next_line = lines[j].strip()
                    if not next_line or next_line.startswith("**") or next_line.startswith("参数"):
                        break
                    prompt_lines.append(next_line)
            if scenes:
                scenes[-1]["negative_prompt"] = " ".join(prompt_lines)

    return scenes


def extract_sdxl_prompts_from_json(workflow_dir):
    """
    从剧本输出目录的工作流 JSON 中提取提示词

    参数：
        workflow_dir: 工作流目录（含 scene_XX_wan22_i2v.json）

    返回：
        list[dict]: [{"scene_id": int, "name": str, "motion_prompt": str}]
    """
    scenes = []
    wf_dir = Path(workflow_dir)
    if not wf_dir.exists():
        return scenes

    for json_file in sorted(wf_dir.glob("scene_*_wan22_i2v.json")):
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        scene_id = data.get("scene_id", 0)
        scene_name = data.get("scene_name", f"第{scene_id}场")
        motion_prompt = data.get("motion_prompt", "")

        # 从 motion_prompt 反推图片描述（去掉运动词汇）
        image_prompt = motion_prompt
        for word in ["slowly", "slow motion", "walking", "standing up", "turning",
                      "zoom in", "zoom out", "push in", "camera", "panning"]:
            image_prompt = image_prompt.replace(word, "").strip()
        image_prompt = image_prompt.strip(", ").strip()

        scenes.append({
            "scene_id": scene_id,
            "name": scene_name,
            "motion_prompt": motion_prompt,
            "image_prompt": image_prompt or motion_prompt,
        })

    return scenes


def generate_storyboard_images(script_path, output_dir, comfyui_url=None,
                                lora_params=None, ipadapter_params=None,
                                batch_per_scene=DEFAULT_BATCH_PER_SCENE,
                                reference_image=None):
    """
    自动生成分镜图（租算力 SDXL + LoRA 锁人）

    参数：
        script_path:       剧本文件路径
        output_dir:        图片输出目录
        comfyui_url:       ComfyUI API 地址（默认读 config）
        lora_params:       LoRA 锁人参数
        ipadapter_params:  IP-Adapter 锁脸参数
        batch_per_scene:   每场抽卡数量
        reference_image:   参考人脸图片（IP-Adapter 用）

    返回：
        list[str]: 生成的图片路径列表
    """
    from comfyui_api import check_comfyui_running, submit_workflow, poll_prompt_status, get_output_images

    comfyui_url = comfyui_url or config.COMFYUI_API_URL
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 检查 ComfyUI 是否在线
    if not check_comfyui_running(comfyui_url):
        print(f"  ✗ ComfyUI 服务未运行 ({comfyui_url})")
        print("  📋 请确保租算力机上的 ComfyUI 已启动并监听正确端口")
        return []

    print(f"  ✓ ComfyUI 已连接 ({comfyui_url})")

    # 提取提示词
    scenes = extract_sdxl_prompts_from_script(script_path)
    if not scenes:
        print("  ⚠ 未从剧本中提取到 SDXL 提示词")
        print("  💡 正在尝试从工作流 JSON 提取...")
        scenes = extract_sdxl_prompts_from_json(str(output_dir / "workflows"))

    if not scenes:
        print("  ✗ 无法提取提示词，请检查剧本格式")
        return []

    print(f"  ✓ 提取到 {len(scenes)} 场提示词")

    # 设置参考图（IP-Adapter）
    if reference_image and ipadapter_params:
        ipadapter_params["reference_image"] = reference_image

    # SDXL 通用反向提示词
    negative_prompt = (
        "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, "
        "fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, "
        "signature, watermark, blurry, deformed, ugly, duplicate, morbid, mutilated, "
        "out of frame, extra limbs, cloned face, disfigured, gross proportions, "
        "malformed limbs, missing arms, missing legs, extra arms, extra legs, "
        "mutated hands, fused fingers, too many fingers, long neck, horizontal frame, "
        "landscape orientation"
    )

    # 逐场生成
    all_images = []
    total_start = time.time()

    for scene in scenes:
        scene_id = scene["scene_id"]
        scene_name = scene["name"]
        positive = scene.get("positive_prompt", scene.get("image_prompt", ""))

        if not positive:
            print(f"  ⚠ 第{scene_id}场无提示词，跳过")
            continue

        print(f"\n  🎬 第{scene_id}场: {scene_name}")
        print(f"     提示词: {positive[:80]}...")

        generated = []

        for batch_idx in range(batch_per_scene):
            # 每次不同 seed
            seed = int(time.time() * 1000) % (2**32)

            output_prefix = f"scene_{scene_id:02d}_{scene_name}_batch{batch_idx+1}"

            workflow = build_sdxl_workflow(
                positive_prompt=positive,
                negative_prompt=negative_prompt,
                output_path=output_prefix,
                lora_params=lora_params,
                ipadapter_params=ipadapter_params,
                scene_id=scene_id,
            )

            # 设置 seed
            workflow["3"]["inputs"]["seed"] = seed

            try:
                prompt_id = submit_workflow(workflow, comfyui_url)
                print(f"     📤 已提交 (seed={seed})")

                result = poll_prompt_status(prompt_id, comfyui_url, timeout=300, poll_interval=3)

                if result.get("status") == "completed":
                    images = get_output_images(prompt_id, comfyui_url, output_dir=str(output_dir))
                    if images:
                        print(f"     ✅ 生成成功: {Path(images[0]).name}")
                        generated.append(images[0])
                    else:
                        print(f"     ⚠ 生成完成但未获取到图片")
                else:
                    print(f"     ✗ 生成失败: {result.get('error', '未知错误')}")

            except Exception as e:
                logger.error(f"第{scene_id}场 batch{batch_idx+1} 生成失败: {e}")
                print(f"     ✗ 异常: {e}")

        if generated:
            all_images.extend(generated)
            print(f"  📊 第{scene_id}场: 生成 {len(generated)}/{batch_per_scene} 张成功")
            print(f"     💡 请人工筛选最优图片，重命名为 scene_{scene_id:02d}_selected.png")
        else:
            print(f"  ❌ 第{scene_id}场: 全部失败")

    total_time = time.time() - total_start
    print(f"\n  📊 分镜图生成完成: {len(all_images)} 张, 耗时 {total_time//60:.0f}分{total_time%60:.0f}秒")

    # 成本估算
    cost = (total_time / 3600) * config.COST_PER_HOUR
    print(f"  💰 本次成本: 约 ¥{cost:.2f}")

    return all_images


def build_character_consistency_prompt(base_prompt, character_desc, lora_tag=None):
    """
    为提示词添加人物一致性关键词

    参数：
        base_prompt:    原始提示词
        character_desc: 人物描述（如 "beautiful chinese woman, long black hair, red lips"）
        lora_tag:       LoRA 触发词（如果 LoRA 有特定触发词）

    返回：
        增强后的提示词
    """
    parts = [base_prompt]

    # 添加人物描述
    if character_desc:
        parts.append(character_desc)

    # LoRA 触发词
    if lora_tag:
        parts.insert(0, lora_tag)

    # 人物一致性增强词
    consistency_keywords = [
        "same person",
        "consistent face",
        "consistent features",
        "same clothing",
        "same hairstyle",
    ]
    parts.extend(consistency_keywords)

    return ", ".join(parts)


# ============ 独立运行入口 ============

def main():
    parser = argparse.ArgumentParser(description="文生图自动化（租算力 SDXL + LoRA 锁人）")
    parser.add_argument("--script", required=True, help="剧本 .md 文件路径")
    parser.add_argument("--output", help="图片输出目录（默认: output/storyboard_images/）")
    parser.add_argument("--comfyui-url", help="ComfyUI API 地址（默认读 config）")
    parser.add_argument("--lora", help="LoRA 模型文件名（如 face_lora.safetensors）")
    parser.add_argument("--lora-strength", type=float, default=0.8, help="LoRA 强度 (0.5-1.0)")
    parser.add_argument("--reference", help="参考人脸图片路径（IP-Adapter 用）")
    parser.add_argument("--batch", type=int, default=3, help="每场抽卡数量")
    parser.add_argument("--no-lora", action="store_true", help="不使用 LoRA")

    args = parser.parse_args()

    output_dir = args.output or str(config.OUTPUT_DIR / "storyboard_images")

    lora_params = None
    if not args.no_lora and args.lora:
        lora_params = {
            "lora_name": args.lora,
            "strength_model": args.lora_strength,
            "strength_clip": args.lora_strength,
        }
        print(f"  🔒 人物锁人: LoRA ({args.lora}, 强度 {args.lora_strength})")
    elif not args.no_lora:
        print(f"  🔒 人物锁人: 使用默认 LoRA ({DEFAULT_LORA_PARAMS['lora_name']})")
        lora_params = DEFAULT_LORA_PARAMS

    ipadapter_params = None
    if args.reference:
        ipadapter_params = DEFAULT_IPADAPTER_PARAMS
        print(f"  🔒 参考图锁脸: {args.reference}")

    print(f"\n{'='*50}")
    print(f"  文生图自动化 — 租算力 SDXL + LoRA 锁人")
    print(f"{'='*50}")
    print(f"  剧本: {args.script}")
    print(f"  输出: {output_dir}")
    print(f"  每场抽卡: {args.batch} 张")
    print(f"  硬件: 云GPU RTX 4090 (租算力)")
    print(f"{'='*50}\n")

    images = generate_storyboard_images(
        script_path=args.script,
        output_dir=output_dir,
        comfyui_url=args.comfyui_url,
        lora_params=lora_params,
        ipadapter_params=ipadapter_params,
        batch_per_scene=args.batch,
        reference_image=args.reference,
    )

    if images:
        print(f"\n  ✅ 成功生成 {len(images)} 张分镜图")
        print(f"  📁 输出目录: {output_dir}")
        print(f"  💡 下一步: 人工筛选最优图片 → Wan2.2 I2V 生视频")
    else:
        print(f"\n  ❌ 未生成任何图片，请检查 ComfyUI 连接和模型文件")


if __name__ == "__main__":
    main()
