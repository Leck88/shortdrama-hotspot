# shortdrama-hotspot

**短剧热点监控 + 仿制剧本 + TTS配音先行 + SDXL文生图(LoRA锁人) + Wan2.2 图生视频（5秒分段）** —— 从热点发现到成品视频的完整闭环。

核心变化（v5.2）：**SDXL自动化文生图 + LoRA锁人 + 租算力跑 Wan2.2 + 5秒分段 + 尾帧续写拼接**。

```
热点监控 → 爆款拆解 → 仿制剧本 → TTS配音(先行)
                                       ↓
                         SDXL文生图(768x1344, LoRA锁人, 每场3张抽卡)
                                       ↓
                              人工筛选最优分镜图
                                       ↓
                         Wan2.2 I2V 5秒/段 → 尾帧续写 → 交叉淡化拼接
                                       ↓
                              字幕/合成 → 成品视频
```

## 完整8步流程

```
步骤1: 抓取热点（酷乐API + 抖音热搜）
步骤2: 仿制剧本（含对白/旁白 + SDXL提示词 + LoRA锁人词）
步骤3: TTS配音先行（Edge TTS/CosyVoice，音频时长决定分镜节奏）
步骤4: SDXL文生图（768x1344竖屏, LoRA锁人, 每场3张抽卡, 租算力4090）
步骤5: 人工筛选分镜图（或自动筛选最优）
步骤6: Wan2.2 I2V（5秒/段, FP16直出, 尾帧续写）
步骤7: 字幕生成（SRT格式，基于TTS时长精确生成时间轴）
步骤8: FFmpeg拼接合成（多段5秒 + 交叉淡化 → 15秒+成片）
```

## SDXL文生图 + LoRA锁人（v5.2核心新增）

### 为什么需要LoRA锁人？

短剧5场分镜，每场都是同一批人物。如果不锁人，不同场次的人物脸型、发型、穿着可能不一致，成片一看就是AI。

### 锁人策略

| 方案 | 原理 | 效果 | 难度 |
|---|---|---|---|
| **LoRA** | 训练一个人物小模型，挂在SDXL后面 | 脸型/发型/穿着高度一致 | 中（需训练LoRA） |
| **IP-Adapter** | 给一张参考人脸图，让SDXL模仿 | 脸型相似，但不完美 | 低（只需一张参考图） |
| **提示词锁人** | 所有场次使用相同外貌描述词 | 基础一致性，免费 | 低（已内置） |

**本项目三种方式都支持**，推荐 LoRA + 提示词锁人 组合使用。

### 提示词锁人示例

每场SDXL提示词末尾自动追加：
```
same person in all scenes, consistent facial features, consistent eye color,
consistent hairstyle, consistent clothing style, consistent skin tone,
identical appearance across scenes
```

### LoRA 配置

在 `config.py` 或环境变量中设置：

| 配置项 | 环境变量 | 默认值 | 说明 |
|---|---|---|---|
| LoRA文件 | `SHORTDRAMA_LORA_NAME` | `face_lora.safetensors` | 放在 `ComfyUI/models/loras/` |
| LoRA强度 | `SHORTDRAMA_LORA_STRENGTH` | `0.8` | 0.5-1.0，越高越像 |
| 参考人脸 | `SHORTDRAMA_REFERENCE_FACE` | 空 | IP-Adapter锁脸用 |

## 5秒分段策略

**不要一次生成15秒。拆成 5秒 + 5秒 + 5秒，尾帧接力，交叉淡化拼接。**

| 单段长度 | 质量 | 成功率 | 一致性 | 推荐 |
|---|---|---|---|---|
| 3秒 | 极高 | 极高 | 极高 | 可用 |
| **5秒** | **高** | **高** | **高** | **最佳平衡** |
| 8秒 | 中 | 中 | 中 | 不推荐 |
| 10秒+ | 低 | 低 | 低 | 不推荐 |

### 怎么拼？

```
分镜图1 → Wan2.2 I2V → 片段1 (0-5s)
                              ↓
                         提取尾帧（最后5帧）
                              ↓
尾帧 = 分镜图2 → Wan2.2 I2V → 片段2 (5-10s)
                              ↓
                         提取尾帧
                              ↓
尾帧 = 分镜图3 → Wan2.2 I2V → 片段3 (10-15s)
                              ↓
                    交叉淡化重叠 0.5秒
                              ↓
                         15秒成片
```

**ComfyUI 插件**：使用 `ComfyUI-WanVideoStartEndFrames` 实现尾帧续写。

## 硬件与成本

### 推荐租算力配置

| 显卡 | 显存 | SDXL文生图 | Wan2.2 5秒视频 | 时租 | 推荐度 |
|---|---|---|---|---|---|
| **RTX 4090** | **24GB** | **10-20秒/张** | **3-6分钟** | **¥4-8** | **首选** |
| RTX 5090 | 32GB | 5-10秒/张 | 2-4分钟 | ¥8-15 | 速度最快 |

### 成本对比（15秒成片 = 3段 x 5秒）

| 方案 | SDXL | Wan2.2 | 总成本 | 日产100条 |
|---|---|---|---|---|
| 开源全链路 | ¥0.2-0.5 | ¥4.5-9.0 | **¥5-10** | **¥500-1000** |
| 闭源：Kling/Seedance | - | - | ¥10-30/条 | ¥1000-3000 |

**全链路开源仍比闭源便宜3-6倍。**

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/Leck88/shortdrama-hotspot.git
cd shortdrama-hotspot
```

### 2. 查看今日热点（零依赖）

```bash
python fetch_hotspot.py
```

### 3. 生成仿制剧本（含SDXL提示词+LoRA锁人词）

```bash
python fetch_hotspot.py --script        # 自动选最热题材
python fetch_hotspot.py --script --genre "霸总"
python fetch_hotspot.py --script --batch # 批量生成5个
```

### 4. 一键Pipeline

```bash
# 全自动（8步）：热点→剧本→TTS→SDXL文生图→Wan2.2生视频→字幕→合成
python pipeline.py --auto --run-comfyui

# 全自动 + TTS配音 + 字幕
python pipeline.py --auto --run-comfyui --tts

# 仅热点+剧本+TTS（不含生图生视频）
python pipeline.py --auto

# 成本估算
python pipeline.py --cost-estimate
```

### 5. 单独文生图（调试用）

```bash
python scripts/generate_images.py \
  --script output/scripts/婚恋_xxx_2026-07-11.md \
  --lora face_lora.safetensors \
  --lora-strength 0.8 \
  --batch 3
```

## 配置参考（config.py）

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `SHORTDRAMA_OUTPUT_DIR` | `./output` | 输出根目录 |
| `COMFYUI_API_URL` | `http://127.0.0.1:8188` | ComfyUI API地址 |
| `SHORTDRAMA_COST_PER_HOUR` | `6.0` | 云GPU时租（元） |
| `SHORTDRAMA_LORA_NAME` | `face_lora.safetensors` | LoRA模型文件名 |
| `SHORTDRAMA_LORA_STRENGTH` | `0.8` | LoRA强度 |
| `SHORTDRAMA_SDXL_BATCH` | `3` | 每场抽卡数量 |
| `SHORTDRAMA_SDXL_CHECKPOINT` | `sd_xl_base_1.0.safetensors` | SDXL模型 |

## 降低崩脸/变形的6条硬规则

1. **每段只做一个动作**："slowly turning head" ✓  vs  "turn head + smile + wave" ✗
2. **运动幅度压低**：motion_strength = **0.4**（默认0.8容易崩）
3. **每段抽卡3-5条**：选最优，删其余
4. **固定种子接力**：第一段 seed，第二段用 seed±5
5. **人物加LoRA锁脸**：固定角色提前炼Face LoRA
6. **崩了只重跑那一段**：分段的好处

## 项目结构

```
shortdrama-hotspot/
├── fetch_hotspot.py          # 热点抓取+日报生成
├── pipeline.py               # 一键Pipeline（8步完整流程）
├── config.py                 # 集中配置（路径/参数/API/LoRA/成本）
├── requirements.txt
├── scripts/
│   ├── generate_script.py    # 剧本生成（含SDXL提示词+LoRA锁人词）
│   ├── generate_images.py    # SDXL文生图自动化（租算力+LoRA锁人）★新增
│   ├── comfyui_api.py        # ComfyUI API交互
│   └── tts_subtitle.py       # TTS配音+字幕生成
├── utils/
│   ├── genre.py              # 题材分类
│   └── api_helpers.py        # API请求辅助
├── templates/
│   ├── genre_templates.json  # 10种题材剧本模板
│   └── comfyui_pipeline_config.json
├── workflows/                 # ComfyUI工作流JSON
└── tests/
    ├── test_genre.py
    └── test_config.py
```

## 常见问题

**Q: LoRA怎么训练？**

用 `kohya_ss` 或 `sd-scripts`，20-30张人脸照片即可训练一个SDXL LoRA。训练约30-60分钟（4090）。

**Q: 没有LoRA怎么办？**

项目内置了提示词锁人（same person / consistent face），基础可用。效果不如LoRA但免费。

**Q: IP-Adapter和LoRA可以同时用吗？**

可以。在 `config.py` 中设置 `SHORTDRAMA_REFERENCE_FACE` 指向参考人脸图片即可。

**Q: 热点API不稳定怎么办？**

内置3次重试+60分钟缓存。同一小时内重复请求直接读缓存。

## License

MIT

## 更新日志

### v5.2 (2026-07-11)

- **SDXL文生图自动化**: 新增 `scripts/generate_images.py`，租算力跑SDXL
- **LoRA锁人**: 所有场次自动使用同一LoRA，保证人物一致性
- **IP-Adapter锁脸**: 可选参考图锁脸，与LoRA互补
- **提示词锁人**: 每场SDXL提示词自动追加 same person / consistent face
- **8步流程**: 从7步扩展为8步，SDXL自动生图替代手动准备
- **成本模型更新**: 包含SDXL文生图耗时和费用

### v5.1 (2026-07-11)

- 租算力方案、5秒分段、尾帧续写、文生图外置

### v5.0 (2026-06-02)

- 配音先行流程重构

### v4.1 (2026-05-23)

- 架构重构：config.py、共享模块、Bug修复、单元测试
