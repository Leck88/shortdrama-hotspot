# shortdrama-hotspot

**短剧热点监控 + 仿制剧本 + SDXL文生图(LoRA锁人) + Wan2.2 图生视频（5秒分段）** —— 从热点发现到成品视频的完整闭环。

v5.3 核心理念：**租算力现成镜像/工作流 + 6步自动化 + TTS手动**。

```
热点监控 → 仿制剧本 → SDXL文生图(现成镜像, LoRA锁人)
                                    ↓
                           人工筛选最优分镜图
                                    ↓
                   Wan2.2 I2V 5秒/段(现成工作流) → 尾帧续写 → 交叉淡化拼接
                                    ↓
                           字幕/合成 → 成品视频

手动: TTS配音（待搞懂后接入自动化）
```

## 6步自动化 + 手动TTS

```
自动化（python pipeline.py --auto --run-comfyui）：
  1. 抓取热点（酷乐API + 抖音热搜）
  2. 仿制剧本（含SDXL提示词 + LoRA锁人词 + Wan2.2运动词）
  3. SDXL文生图（租算力现成镜像, 832x1472, LoRA锁人, 每场3张抽卡）
  4. Wan2.2 I2V（租算力现成工作流, 5秒/段, FP16直出, 每段抽卡3条）
  5. 尾帧续写 + 交叉淡化拼接（3段x5秒 → 15秒成片）
  6. FFmpeg合成 → 成品视频

手动：
  - TTS配音：待搞懂后接入自动化，当前手动处理
  - 分镜图筛选：每场3张抽卡后人工选最优
```

## 租算力使用方式（现成镜像+工作流）

AutoDL/极智算等平台已有现成 **ComfyUI 镜像**，内置：
- SDXL Checkpoint（JuggernautXL / RealVisXL / Flux.1-dev）
- LoRA 加载节点
- IP-Adapter 节点
- Wan2.2 I2V 工作流
- 尾帧续写插件

**开机即用，无需自己搭建环境或手写 workflow JSON。**

从剧本中复制提示词粘贴到现成工作流即可运行。

## 文生图底模推荐（4090 FP16直出）

| 排名 | 模型 | 分辨率 | 步数 | 速度 | 画质 |
|---|---|---|---|---|---|
| **1** | **Flux.1-dev** | 1024x1536 | 28 | 20-60秒 | 画质天花板 |
| **2** | **JuggernautXL v35** | 832x1472 | 35 | 15-30秒 | 写实最强SDXL微调 |
| **3** | **RealVisXL V5.0** | 832x1472 | 35 | 15-30秒 | 人物写真专用 |
| 4 | SDXL Base 1.0 | 832x1472 | 35 | 15-30秒 | 基线 |

**4090 24GB 全部可 FP16 直出，不需要量化。**

## LoRA 锁人

| 配置项 | 环境变量 | 默认值 |
|---|---|---|
| LoRA文件 | `SHORTDRAMA_LORA_NAME` | `face_lora.safetensors` |
| LoRA强度 | `SHORTDRAMA_LORA_STRENGTH` | `0.8` |
| 参考人脸(IP-Adapter) | `SHORTDRAMA_REFERENCE_FACE` | 空 |

提示词自动追加: `same person / consistent face / consistent features / consistent clothing`

## 5秒分段 + 尾帧续写拼接

```
分镜图1 → Wan2.2 I2V → 片段1 (0-5s) → 提取尾帧
                                        ↓
尾帧 = 分镜图2 → Wan2.2 I2V → 片段2 (5-10s) → 提取尾帧
                                                  ↓
                                        片段3 (10-15s) → 交叉淡化0.5s → 15秒成片
```

## 硬件与成本

| 显卡 | 显存 | SDXL | Wan2.2 5秒 | 时租 | 单集成本 |
|---|---|---|---|---|---|
| **RTX 4090** | **24GB** | **15-30秒/张** | **3-6分钟** | **¥4-8** | **¥5-10** |

## 快速开始

```bash
# 1. 克隆项目
git clone https://github.com/Leck88/shortdrama-hotspot.git
cd shortdrama-hotspot

# 2. 查看热点（零依赖）
python fetch_hotspot.py

# 3. 生成剧本（含SDXL提示词+LoRA锁人词）
python fetch_hotspot.py --script

# 4. 自动化Pipeline（热点→剧本→SDXL+Wan2.2）
python pipeline.py --auto --run-comfyui

# 5. 成本估算
python pipeline.py --cost-estimate
```

## 项目结构

```
shortdrama-hotspot/
├── pipeline.py               # 一键Pipeline（6步自动化）
├── fetch_hotspot.py           # 热点抓取+日报
├── config.py                 # 配置（LoRA/SDXL/成本/租算力）
├── scripts/
│   ├── generate_script.py    # 剧本（SDXL提示词+LoRA锁人词+Wan2.2运动词）
│   ├── generate_images.py    # SDXL文生图（LoRA锁人+IP-Adapter）
│   ├── comfyui_api.py        # ComfyUI API
│   └── tts_subtitle.py       # TTS（手动阶段）
├── utils/                    # 共享模块
├── templates/                # 10种题材模板
└── workflows/                # ComfyUI工作流（参考）
```

## License

MIT

## 更新日志

### v5.3 (2026-07-11)

- TTS改为手动步骤（待后续接入）
- SDXL/Wan2.2步骤引导使用租算力现成镜像和工作流
- 不再自建workflow JSON，用平台现成工作流
- 流程精简为6步自动化 + 2步手动
- 底模推荐：JuggernautXL / Flux.1-dev / RealVisXL

### v5.2 (2026-07-11)

- SDXL文生图自动化 + LoRA锁人 + 8步流程

### v5.1 (2026-07-11)

- 租算力方案 + 5秒分段 + 尾帧续写

### v5.0 (2026-06-02)

- 配音先行流程重构
