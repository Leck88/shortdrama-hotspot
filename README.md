# shortdrama-hotspot

**短剧热点监控 + 仿制剧本 + TTS配音先行 + Wan2.2 图生视频（5秒分段）** —— 从热点发现到成品视频的完整闭环。

核心变化（v5.1）：**文生图外置 + 租算力跑 Wan2.2 + 5秒分段 + 尾帧续写拼接**。

```
热点监控 → 爆款拆解 → 仿制剧本 → TTS配音(先行) → 【你准备分镜图】
                                                    ↓
                                          Wan2.2 I2V 5秒/段 → 尾帧续写 → 交叉淡化拼接
                                                    ↓
                                          字幕/合成 → 成品视频
```

## 为什么要改？

| 项目 | v5.0（本地5060Ti） | v5.1（租算力4090） |
|---|---|---|
| 硬件 | RTX 5060 Ti 16GB | **云GPU RTX 4090 24GB** |
| 生图 | SDXL本地跑 | **文生图外置，你自行搞定** |
| 视频时长 | 8秒/段 | **5秒/段（更稳定）** |
| 精度 | FP8/GGUF量化 | **FP16直出（画质更好）** |
| 单条成本 | ~0.9元 | **~0.3-0.8元** |
| 长视频 | 直接生成，易崩 | **尾帧续写+拼接，可控** |
| 稳定性 | 5060Ti易爆显存 | **4090稳，可24小时跑** |

## 5秒分段策略（核心）

**不要一次生成15秒。拆成 5秒 + 5秒 + 5秒，尾帧接力，交叉淡化拼接。**

### 为什么5秒最好？

扩散模型误差随时间累积。时间越长，越容易出现：人脸漂移、手脚变形、衣服纹理错乱。

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

| 显卡 | 显存 | 5秒生成时间 | 时租 | 单条成本 | 推荐度 |
|---|---|---|---|---|---|
| RTX 4080 | 16GB | 需量化，易报错 | ¥3-5 | ¥0.5-1.2 | 不推荐 |
| **RTX 4090** | **24GB** | **3-6分钟** | **¥4-8** | **¥0.3-0.8** | **首选** |
| RTX 4090 48G | 48GB | 3-6分钟 | ¥10-18 | ¥0.8-2.5 | 不推荐（速度同24G） |
| RTX 5090 | 32GB | 2-4分钟 | ¥8-15 | ¥0.4-1.0 | 速度最快，适合赶工 |

### 租算力平台

| 平台 | 4090时租 | 特点 |
|---|---|---|
| **AutoDL** | ¥4-8 | 最稳定，有现成ComfyUI镜像，按秒计费 |
| 极智算 | 略低 | 长租划算 |
| 算家云 | ¥1.24起 | 最便宜，但资源紧张 |

### 成本对比（15秒成片 = 3段×5秒）

| 方案 | 15秒成本 | 日产100条 |
|---|---|---|
| 开源：Wan2.2 + 租4090 | ¥1-2（含抽卡3条） | ¥100-200 |
| 闭源：Kling / Seedance | ¥10-30 | ¥1000-3000 |

**差距约10倍。**

## 降低崩脸/变形的6条硬规则

1. **每段只做一个动作**："slowly turning head" ✓  vs  "turn head + smile + wave" ✗
2. **运动幅度压低**：motion_strength = **0.4**（默认0.8容易崩）
3. **每段抽卡3-5条**：选最优，删其余
4. **固定种子接力**：第一段 seed，第二段用 seed±5
5. **人物加LoRA锁脸**：固定角色提前炼Face LoRA
6. **崩了只重跑那一段**：分段的好处

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

### 3. 生成仿制剧本（含ComfyUI I2V配置）

```bash
python fetch_hotspot.py --script        # 自动选最热题材
python fetch_hotspot.py --script --genre "霸总"
python fetch_hotspot.py --script --batch # 批量生成5个
```

### 4. 一键Pipeline

```bash
# 仅热点+剧本+TTS先行
python pipeline.py --auto

# 指定题材
python pipeline.py --auto --genre "婚恋"

# 完整流程：热点→剧本→TTS先行→生视频（需ComfyUI服务运行中）
python pipeline.py --auto --run-comfyui

# 全套：+字幕+合成
python pipeline.py --auto --run-comfyui --tts

# 从已有剧本开始
python pipeline.py --from-script <剧本.md> --run-comfyui

# 成本估算
python pipeline.py --cost-estimate
```

## 完整7步流程

```
步骤1: 抓取热点（热度榜+抖音热搜）
步骤2: 仿制剧本（含对白/旁白 + Wan2.2运动提示词）
步骤3: TTS配音先行（Edge TTS/CosyVoice，音频时长决定分镜节奏）
步骤4: 分镜规划 + 准备分镜图（文生图由你自行搞定）
步骤5: Wan2.2 I2V（5秒/段，FP16直出，尾帧续写）
步骤6: 字幕生成（SRT格式，基于TTS时长精确生成时间轴）
步骤7: FFmpeg拼接合成（多段5秒 + 交叉淡化 → 15秒+成片）
```

## 配置参考（config.py）

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `SHORTDRAMA_OUTPUT_DIR` | `./output` | 输出根目录 |
| `COMFYUI_API_URL` | `http://127.0.0.1:8188` | ComfyUI API地址 |
| `SHORTDRAMA_COST_PER_HOUR` | `6.0` | 云GPU时租（元） |
| `SHORTDRAMA_API_TIMEOUT` | `15` | API超时（秒） |
| `SHORTDRAMA_API_RETRIES` | `3` | API重试次数 |

## ComfyUI 工作流文件

| 文件 | 功能 | 备注 |
|---|---|---|
| `workflows/wan22_i2v_1080p_8s.json` | Wan2.2 I2V 图生视频 | 改 frames=81, fps=16 即为5秒 |
| `workflows/sdxl_wan22_combined.json` | 组合工作流 | 如需SDXL可保留 |

**Wan2.2 关键参数**：
- frames: **81** (5秒@16fps)
- motion_strength: **0.4**
- cfg_scale: **6.5**
- 模型: Wan2.2-I2V-14B-480P FP16
- 输入图: 你的分镜图（768x1344+ 竖屏）

## 项目结构

```
shortdrama-hotspot/
├── fetch_hotspot.py          # 热点抓取+日报生成
├── pipeline.py               # 一键Pipeline（7步完整流程）
├── config.py                 # 集中配置（路径/参数/API地址/成本）
├── requirements.txt
├── scripts/
│   ├── generate_script.py    # 剧本生成（含Wan2.2 I2V配置）
│   ├── comfyui_api.py        # ComfyUI API交互
│   └── tts_subtitle.py       # TTS配音+字幕生成
├── utils/
│   ├── genre.py              # 题材分类
│   └── api_helpers.py        # API请求辅助
├── templates/
│   ├── genre_templates.json  # 10种题材剧本模板
│   └── comfyui_pipeline_config.json
├── workflows/
│   ├── wan22_i2v_1080p_8s.json
│   └── sdxl_wan22_combined.json
└── tests/
    ├── test_genre.py
    └── test_config.py
```

## 常见问题

**Q: 16GB显存本地能跑吗？**

能，但体验不佳。需要开FP8/量化，分辨率受限。建议租4090。

**Q: 文生图用什么工具？**

随意。Midjourney、Stable Diffusion、Flux、即梦、可灵……只要输出768x1344+竖屏图即可。

**Q: 热点API不稳定怎么办？**

内置3次重试+60分钟缓存。同一小时内重复请求直接读缓存。

**Q: 5秒会不会太短？**

短视频本身很少一个镜头连续15秒。多镜头+转场+音效，节奏更好，用户留存更高。

**Q: 怎么批量自动化？**

ComfyUI API + 自动队列 + 失败重试 + 自动拼接。可用 `comfy-cli` 或直接POST workflow JSON。

## License

MIT

## 更新日志

### v5.1 (2026-07-11)

- **租算力方案**: 从本地5060Ti改为云GPU RTX 4090/5090租赁
- **5秒分段**: 视频从8秒改为5秒/段，稳定性更高
- **尾帧续写**: 新增分段拼接策略，交叉淡化重叠0.5秒
- **文生图外置**: 去掉SDXL，分镜图由用户自行准备
- **成本重构**: 单条5秒视频约 ¥0.3-0.8，比闭源便宜10倍
- **FP16直出**: 4090 24GB无需量化，画质更好
- **运动幅度降低**: motion_strength从0.8改为0.4，崩脸率大幅下降

### v5.0 (2026-06-02)

- 配音先行流程重构
- 从剧本→TTS→分镜→视频→合成

### v4.2 (2026-05-25)

- 新增本地硬件部署指南（5060Ti）
- 新增16GB显存优化方案

### v4.1 (2026-05-23)

- 架构重构：config.py、共享模块、Bug修复、单元测试
