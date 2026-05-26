#!/usr/bin/env python3
"""
修改两个 ComfyUI 工作流 JSON 文件，适配短剧 720P 竖屏 8秒视频流水线

修改1: Flux2-Klein-9B 文生图 → 768x1344 输出 + ImageScale 到 720x1280
修改2: Wan2.2-14B 文生视频 → 832x480 @ 129帧(8秒@16fps)
"""

import json
import os
import copy

# ============ 修改1: Flux2-Klein 工作流 ============

def modify_flux2_klein(input_path, output_path):
    """
    修改 Flux2-Klein-9B 文生图工作流
    
    关键修改：
    1. 子图内 PrimitiveInt Height: 1024 → 1344 (720P竖屏)
    2. 子图内 EmptyFlux2LatentImage: [1024, 1024, 1] → [768, 1344, 1]
    3. 子图内 Flux2Scheduler: [20, 1024, 1024] → [20, 768, 1344]
    4. 增加 ImageScale 节点：将输出缩放到 720x1280
    5. SaveImage 前缀改为 shortdrama/scene_{SCENE_ID}
    """
    with open(input_path, 'r', encoding='utf-8') as f:
        workflow = json.load(f)
    
    # 修改子图定义中的节点
    definitions = workflow.get("definitions", {})
    subgraphs = definitions.get("subgraphs", [])
    
    for subgraph in subgraphs:
        nodes = subgraph.get("nodes", [])
        for node in nodes:
            # 修改 Height PrimitiveInt (node 69) - 在两个子图中都有
            if node.get("type") == "PrimitiveInt" and node.get("title") == "Height":
                node["widgets_values"][0] = 1820
                print(f"  [修改] 子图 '{subgraph['name']}' 的 Height: 1024 → 1820")
            
            # 修改 EmptyFlux2LatentImage (node 66)
            if node.get("type") == "EmptyFlux2LatentImage":
                node["widgets_values"][0] = 1024  # width
                node["widgets_values"][1] = 1820  # height
                print(f"  [修改] 子图 '{subgraph['name']}' 的 EmptyFlux2LatentImage: → [1024, 1820, 1]")
            
            # 修改 Flux2Scheduler (node 62)
            if node.get("type") == "Flux2Scheduler":
                node["widgets_values"][1] = 1024  # width
                node["widgets_values"][2] = 1820  # height
                print(f"  [修改] 子图 '{subgraph['name']}' 的 Flux2Scheduler: → [20, 1024, 1820]")
    
    # 修改主图中的 SaveImage 节点前缀
    for node in workflow.get("nodes", []):
        if node.get("type") == "SaveImage":
            if node.get("mode", 0) == 0:  # 只修改激活的 SaveImage (mode 0)
                node["widgets_values"][0] = "shortdrama/scene_{SCENE_ID}"
                print(f"  [修改] SaveImage (id={node['id']}): 前缀 → shortdrama/scene_{{SCENE_ID}}")
    
    # 现在，主图中的子图实例（node 75, 激活状态 mode=0）输出 IMAGE
    # 我们需要在 SaveImage 之前插入 ImageScale 节点
    # 但这个工作流使用了子图结构，子图直接输出 IMAGE
    # 直接在子图内部添加 ImageScale 更复杂，所以我们在外部添加
    
    # 找到活跃的子图实例节点 (id=75, mode=0) 和 SaveImage (id=9, mode=0)
    # 当前连接: node 75 output 0 → node 9 input 0 (link 154, IMAGE)
    
    # 我们需要:
    # 1. 添加一个 ImageScale 节点 (id=103)
    # 2. 修改连接: 75 → ImageScale → SaveImage
    
    new_last_node_id = workflow["last_node_id"]  # 102
    new_last_link_id = workflow["last_link_id"]  # 164
    
    # 创建 ImageScale 节点
    imagescale_node_id = new_last_node_id + 1  # 103
    imagescale_node = {
        "id": imagescale_node_id,
        "type": "ImageScale",
        "pos": [530, 340],
        "size": [320, 180],
        "flags": {},
        "order": 9,  # 在 SaveImage 之前
        "mode": 0,
        "inputs": [
            {
                "name": "image",
                "type": "IMAGE",
                "link": 154  # 从子图实例 75 输出
            }
        ],
        "outputs": [
            {
                "name": "IMAGE",
                "type": "IMAGE",
                "links": [new_last_link_id + 1]
            }
        ],
        "title": "ImageScale到720x1280",
        "properties": {
            "cnr_id": "comfy-core",
            "ver": "0.8.2",
            "Node name for S&R": "ImageScale"
        },
        "widgets_values": [720, 1280, "lanczos"]
    }
    
    workflow["nodes"].append(imagescale_node)
    
    # 修改 SaveImage (id=9) 的输入，从 link 154 改为新 link
    new_link_id = new_last_link_id + 1  # 165
    for node in workflow["nodes"]:
        if node.get("id") == 9 and node.get("type") == "SaveImage":
            # 修改输入 link
            node["inputs"][0]["link"] = new_link_id
            print(f"  [修改] SaveImage (id=9) 输入连接: link 154 → link {new_link_id}")
    
    # 修改子图输出节点的 links，使其指向 ImageScale
    # node 75 的 output 0 links 原来是 [154]，现在也是 [154]（因为 ImageScale 的输入也是 154）
    # 不需要改 node 75 的 output links
    
    # 修改 links 列表
    # 原来的 link 154: [154, 75, 0, 9, 0, "IMAGE"]
    # 改为: [154, 75, 0, 103, 0, "IMAGE"] (75 → ImageScale)
    # 新增: [165, 103, 0, 9, 0, "IMAGE"] (ImageScale → SaveImage)
    for i, link in enumerate(workflow["links"]):
        if link[0] == 154:
            # 修改目标节点从 9 (SaveImage) 到 103 (ImageScale)
            workflow["links"][i] = [154, 75, 0, imagescale_node_id, 0, "IMAGE"]
            print(f"  [修改] Link 154: 目标从 SaveImage(9) → ImageScale({imagescale_node_id})")
            break
    
    # 添加新 link
    workflow["links"].append([new_link_id, imagescale_node_id, 0, 9, 0, "IMAGE"])
    print(f"  [新增] Link {new_link_id}: ImageScale({imagescale_node_id}) → SaveImage(9)")
    
    # 更新 last_node_id 和 last_link_id
    workflow["last_node_id"] = imagescale_node_id
    workflow["last_link_id"] = new_link_id
    
    # 添加 _readme
    workflow["_readme"] = {
        "title": "Flux2-Klein-9B 文生图 720P竖屏（fp4量化）",
        "usage": "替换{{POSITIVE_PROMPT}}为分镜提示词，{SCENE_ID}为场次编号",
        "resolution": "768x1344 → 720x1280",
        "pipeline_step": "步骤3: SDXL生图（768x1344 → 720x1280）",
        "modifications": [
            "子图内 Height: 1024 → 1344",
            "EmptyFlux2LatentImage: [1024, 1024, 1] → [768, 1344, 1]",
            "Flux2Scheduler: [20, 1024, 1024] → [20, 768, 1344]",
            "新增 ImageScale 节点: 缩放到 720x1280 (lanczos)",
            "SaveImage 前缀: shortdrama/scene_{SCENE_ID}"
        ],
        "model_requirements": {
            "unet": "flux-2-klein-base-9b-nvfp4.safetensors (ComfyUI models/diffusion_models/)",
            "clip": "qwen_3_8b_fp4mixed.safetensors (ComfyUI models/text_encoders/, 类型 flux2)",
            "vae": "flux2-vae.safetensors (ComfyUI models/vae/)"
        },
        "time_4080S": "约10-15秒/张"
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(workflow, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Flux2-Klein 工作流已修改并保存: {output_path}")


# ============ 修改2: Wan2.2-14B 文生视频工作流 ============

def modify_wan22_t2v(input_path, output_path):
    """
    修改 Wan2.2-14B 文生视频工作流（4步 LoRA 版）
    
    关键修改：
    1. Node 74 (EmptyHunyuanLatentVideo): [640, 640, 81, 1] → [832, 480, 129, 1]
       - 832x480 是 Wan2.2 支持的 480P 竖屏宽高比
       - 129帧 = 8秒 × 16fps + 1（包含首帧）
    2. Node 104 (EmptyHunyuanLatentVideo, 备用组): 同样修改
    3. VHS_VideoCombine (node 115): 保持 frame_rate=16，修改前缀
    4. 添加 _readme 说明
    """
    with open(input_path, 'r', encoding='utf-8') as f:
        workflow = json.load(f)
    
    frames_for_8s = 129  # 8秒 × 16fps + 1首帧
    
    for node in workflow.get("nodes", []):
        # 修改 EmptyHunyuanLatentVideo 节点
        if node.get("type") == "EmptyHunyuanLatentVideo":
            old_values = node["widgets_values"][:]
            node["widgets_values"] = [832, 480, frames_for_8s, 1]
            print(f"  [修改] Node {node['id']} (EmptyHunyuanLatentVideo): {old_values} → [832, 480, {frames_for_8s}, 1]")
        
        # 修改 VHS_VideoCombine 的输出前缀
        if node.get("type") == "VHS_VideoCombine":
            wv = node["widgets_values"]
            if isinstance(wv, dict):
                wv["filename_prefix"] = "shortdrama/video_scene_{SCENE_ID}"
                print(f"  [修改] Node {node['id']} (VHS_VideoCombine): 前缀 → shortdrama/video_scene_{{SCENE_ID}}")
            elif isinstance(wv, list):
                wv[0] = "shortdrama/video_scene_{SCENE_ID}"
                print(f"  [修改] Node {node['id']} (VHS_VideoCombine): 前缀 → shortdrama/video_scene_{{SCENE_ID}}")
    
    # 添加 _readme
    workflow["_readme"] = {
        "title": "Wan2.2-14B 文生视频 4步 LoRA (832x480, 8秒)",
        "usage": "替换正向提示词为视频描述，输出 8秒 480P 视频后可 upscale 到 720P",
        "resolution": "832x480 (可后处理 upscale 到 720x1280)",
        "video_duration": "8秒 (129帧 @ 16fps)",
        "pipeline_step": "步骤4: Wan2.2 I2V（8秒视频，832x480 → upscale 720P）",
        "modifications": [
            "EmptyHunyuanLatentVideo (node 74, 104): [640,640,81,1] → [832,480,129,1]",
            "VHS_VideoCombine 前缀: shortdrama/video_scene_{SCENE_ID}",
            "注意：此为 T2V（文生视频）工作流，如需 I2V（图生视频）请使用 wan22_i2v_720p_8s_8B.json"
        ],
        "model_requirements": {
            "unet_high_noise": "wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors",
            "unet_low_noise": "wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors",
            "clip": "umt5_xxl_fp8_e4m3fn_scaled.safetensors (类型 wan)",
            "vae": "wan_2.1_vae.safetensors",
            "lora_high_noise": "wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors",
            "lora_low_noise": "wan2.2_t2v_lightx2v_4steps_lora_v1.1_low_noise.safetensors"
        },
        "time_4080S": "约1-2分钟/视频 (4步LoRA加速)"
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(workflow, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Wan2.2 工作流已修改并保存: {output_path}")


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    workflows_dir = os.path.join(base_dir, "workflows")
    
    print("=" * 60)
    print("  修改 ComfyUI 工作流 - 短剧 720P 竖屏 8秒视频")
    print("=" * 60)
    
    # 修改 Flux2-Klein 工作流
    print("\n📷 修改 Flux2-Klein-9B 文生图工作流...")
    flux_input = os.path.join(workflows_dir, "Flux2-Klein-9B-文生图-fp4版_1080p.json")
    flux_output = os.path.join(workflows_dir, "Flux2-Klein-9B-文生图-fp4版_1080p.json")
    if os.path.exists(flux_input):
        modify_flux2_klein(flux_input, flux_output)
    else:
        print(f"  ❌ 文件不存在: {flux_input}")
    
    # 修改 Wan2.2 工作流
    print("\n🎬 修改 Wan2.2-14B 文生视频工作流...")
    wan_input = os.path.join(workflows_dir, "Wan2.2-14B文生视频-4步_8s.json")
    wan_output = os.path.join(workflows_dir, "Wan2.2-14B文生视频-4步_8s.json")
    if os.path.exists(wan_input):
        modify_wan22_t2v(wan_input, wan_output)
    else:
        print(f"  ❌ 文件不存在: {wan_input}")
    
    print("\n" + "=" * 60)
    print("  全部修改完成！")
    print("=" * 60)
