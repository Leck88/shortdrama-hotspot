# shortdrama-hotspot

**短剧热点监控 + 仿制剧本 + ComfyUI一键生成 + TTS配音+字幕** —— 从热点发现到成品视频的完整闭环。

> 适用于短剧创作者、选题策划、行业研究者。快速掌握短剧市场热点，一键生成AI短剧。

---

## 📦 项目概览

```
热点监控 → 爆款拆解 → 仿制剧本 → SDXL生图 → Wan2.2生视频 → TTS配音 → 字幕合成 → 成品视频
                     ↑ 全部本地运行 · 无需联网（热点抓取除外）
```

---

## 🚀 快速开始（5分钟上手）

### 1. 克隆项目

```bash
git clone https://github.com/Leck88/shortdrama-hotspot.git
cd shortdrama-hotspot
```

### 2. 查看今日热点（无需安装任何依赖）

```bash
python fetch_hotspot.py
```

最快体验项目核心功能，零依赖运行。

### 3. 生成热点日报

```bash
python fetch_hotspot.py --report
```

### 4. 生成仿制剧本

```bash
python fetch_hotspot.py --script
```

---

## 🔥 功能详情

### 🔥 热点监控
- **短剧热度榜 Top30** —— 调用酷乐免费API，获取当日最新短剧热度排名
- **抖音热搜智能筛选** —— 从抖音热搜中自动筛选短剧/影视相关词条（两级关键词匹配 + 误匹配过滤）
- **题材自动分类** —— 根据剧名关键词，将短剧归类为婚恋、霸总、甜宠、逆袭等10种题材
- **结构化日报生成** —— 输出Markdown格式报告，包含热度榜、抖音热搜、题材分布、选题参考

### 🎬 仿制剧本 + ComfyUI配置
- **爆款拆解** —— 分析Top5热门短剧的题材、钩子、命名模式
- **仿制剧本生成** —— 基于爆款拆解+题材模板，生成完整2分钟短剧剧本
- **ComfyUI可执行配置** —— 每场输出SDXL正向/反向提示词 + Wan2.2运动提示词 + 工作流JSON
- **批量生成** —— 基于当日Top5热门题材，批量生成仿制剧本

### 🤖 一键Pipeline（7步完整流程）
```
步骤1: 抓取热点（热度榜+抖音热搜）
步骤2: 仿制剧本（SDXL提示词+Wan2.2运动提示词+ComfyUI工作流JSON）
步骤3: SDXL生图（1024x1820 → 1080x1920）
步骤4: Wan2.2 I2V（8秒视频，832x480 → upscale 1080P）
步骤5: TTS配音（Edge TTS，女主/男主自动分配语音）
步骤6: 字幕生成（SRT格式，可烧录到视频）
步骤7: FFmpeg合成（拼接+配音+字幕 → 成品视频）
```

### 🎙 TTS配音 + 字幕
- **Edge TTS配音** —— 自动从剧本提取对话，按角色分配男女声
- **SRT字幕生成** —— 基于TTS时长精确生成时间轴
- **字幕烧录** —— FFmpeg将字幕烧录到视频中
- **配音合并** —— 按时间轴合并多个配音片段到视频

---

## 🖥️ 本地硬件部署指南

### 推荐配置

| 组件 | 规格 | 说明 |
|------|------|------|
| **GPU** | **RTX 5060 Ti 16GB** | 16GB显存可跑SDXL+Wan2.2（需FP8/GUF量化） |
| **内存** | 32GB DDR5 5600MHz | 充足，满足ComfyUI+模型加载 |
| **硬盘** | ≥100GB 空闲 | 模型文件约占50-80GB |
| **系统** | Windows 10/11 或 Linux | ComfyUI跨平台支持 |
| **Python** | ≥3.10 | |

### 对比：本地 vs 云算力

| 维度 | 本地 5060Ti | 云算力 AutoDL |
|------|-----------|--------------|
| **单集成本** | 电费≈¥0.3 | ≈¥1.95 |
| **速度** | 略慢（FP8量化） | 快（FP16） |
| **灵活性** | 随时可用 | 需开机排队 |
| **隐私** | 数据本地 | 数据上传云端 |
| **长期** | 一次投入长期免费 | 持续付费 |

### 本地环境搭建（完整流程）

#### 1. 安装 ComfyUI

```bash
# 克隆 ComfyUI
git clone https://github.com/comfyanonymous/ComfyUI.git
cd ComfyUI

# 安装依赖
pip install -r requirements.txt
```

#### 2. 下载所需模型

将模型文件放入 ComfyUI 对应目录：

| 模型 | 下载来源 | 放置目录 | 大小 | 备注 |
|------|---------|---------|------|------|
| **SDXL 1.0 base** | [HuggingFace](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0) | `ComfyUI/models/checkpoints/` | ≈7GB | 文生图底模 |
| **SDXL refiner** | [HuggingFace](https://huggingface.co/stabilityai/stable-diffusion-xl-refiner-1.0) | `ComfyUI/models/checkpoints/` | ≈7GB | 可选精炼 |
| **Wan2.2 I2V-14B FP8** | [HuggingFace](https://huggingface.co/Kijai/Wan2.1-I2V-14B-fp8-e4m3fn) | `ComfyUI/models/checkpoints/` | ≈14GB | **16GB显存必选FP8版** |
| **CLIP-ViT-bigG** | [HuggingFace](https://huggingface.co/openai/clip-vit-large-patch14) | `ComfyUI/models/clip/` | ≈2GB | Wan2.2所需 |
| **T5-xxl** | [HuggingFace](https://huggingface.co/google/t5-v1_1-xxl) | `ComfyUI/models/clip/` | ≈11GB | Wan2.2所需 |

> **💡 16GB显存优化建议**：Wan2.2必须使用FP8/GUF量化版，SDXL使用fp16即可。可运行 `python scripts/download_models.py`（见下方说明）。

#### 3. 安装 ComfyUI 自定义节点

| 节点 | 仓库 | 说明 |
|------|------|------|
| ComfyUI-WanVideoWrapper | [GitHub](https://github.com/Kijai/ComfyUI-WanVideoWrapper) | Wan2.2视频生成 |
| ComfyUI-Manager | [GitHub](https://github.com/ltdrdata/ComfyUI-Manager) | 节点管理 |

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/Kijai/ComfyUI-WanVideoWrapper.git
git clone https://github.com/ltdrdata/ComfyUI-Manager.git
pip install -r ComfyUI-WanVideoWrapper/requirements.txt
```

#### 4. 启动 ComfyUI（优化参数）

```bash
# Windows
python main.py --force-fp16 --lowvram --gpu-only

# Linux
python main.py --force-fp16 --lowvram --gpu-only
```

> `--lowvram`：低显存模式，16GB Wan2.2必须开启。
> `--force-fp16`：强制FP16计算，减少显存占用。

#### 5. 验证 ComfyUI 运行

```bash
curl http://127.0.0.1:8188/system_stats
# 返回 JSON 说明启动成功
```

#### 6. 安装项目依赖

```bash
cd shortdrama-hotspot

# 基础功能（零依赖，Python标准库即可）
# 无需安装任何包即可运行热点抓取和日报生成

# TTS配音功能
pip install edge-tts

# FFmpeg（用于视频合成）
# Windows: https://ffmpeg.org/download.html
# Linux: sudo apt install ffmpeg
# macOS: brew install ffmpeg
```

---

## 📋 使用方式

### 查看热点
```bash
python fetch_hotspot.py
```

### 生成日报
```bash
python fetch_hotspot.py --report
```

### 生成剧本（含ComfyUI配置）
```bash
python fetch_hotspot.py --script                   # 自动选最热题材
python fetch_hotspot.py --script --genre "霸总"    # 指定题材
python fetch_hotspot.py --script --batch           # 批量生成5个
```

### 一键Pipeline

```bash
# 仅热点+剧本（不需要ComfyUI）
python pipeline.py --auto

# 指定题材
python pipeline.py --auto --genre "婚恋"

# 完整流程：热点→剧本→生图→生视频
python pipeline.py --auto --run-comfyui

# 全套：+TTS配音+字幕
python pipeline.py --auto --run-comfyui --tts

# 查看成本估算
python pipeline.py --cost-estimate
```

### TTS配音（独立使用）
```python
from tts_subtitle import extract_dialogues, generate_tts, generate_srt

dialogues = extract_dialogues("剧本.md")
tts_results = generate_tts(dialogues, "./tts_output")
srt_path = generate_srt(tts_results, "./output.sub.srt")
```

### ComfyUI API（独立使用）
```python
from comfyui_api import check_comfyui_running, submit_workflow, poll_prompt_status

if check_comfyui_running():
    prompt_id = submit_workflow(workflow_dict)
    result = poll_prompt_status(prompt_id, timeout=600)
```

---

## ⚙️ 配置参考（config.py）

所有配置通过 `config.py` 集中管理，支持环境变量覆盖。

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `SHORTDRAMA_OUTPUT_DIR` | `./output` | 所有输出根目录 |
| `SHORTDRAMA_API_URL` | `https://api.kuleu.com/api/shortdramarank` | 短剧热度榜API |
| `DOUYIN_HOT_API_URL` | `https://v2.xxapi.cn/api/douyinhot` | 抖音热搜API |
| `COMFYUI_API_URL` | `http://127.0.0.1:8188` | ComfyUI API地址 |
| `SHORTDRAMA_API_TIMEOUT` | `15` | API超时（秒） |
| `SHORTDRAMA_API_RETRIES` | `3` | API重试次数 |
| `SHORTDRAMA_LOG_LEVEL` | `INFO` | 日志级别 |
| `SHORTDRAMA_CACHE_EXPIRE` | `60` | 缓存过期（分钟） |
| `SHORTDRAMA_COST_PER_HOUR` | `1.8` | 每小时成本（元） |

示例：修改ComfyUI地址和输出目录
```bash
export COMFYUI_API_URL="http://192.168.1.100:8188"
export SHORTDRAMA_OUTPUT_DIR="/data/shortdrama-output"
python pipeline.py --auto --run-comfyui
```

---

## 🎬 ComfyUI 工作流详解

### 工作流文件

| 文件 | 功能 | 适用场景 |
|------|------|---------|
| `workflows/sdxl_1080p_portrait.json` | SDXL竖屏文生图 | 生成1080x1920分镜图 |
| `workflows/wan22_i2v_1080p_8s.json` | Wan2.2图生视频 | 将分镜图转为8秒视频 |
| `workflows/sdxl_wan22_combined.json` | 组合工作流 | 一步文生视频 |
| `workflows/Flux2-Klein-9B-文生图-fp4版_1080p.json` | Flux模型替代方案 | 16GB显存优化版 |
| `workflows/Wan2.2-14B文生视频-4步_8s.json` | Wan2.2文生视频 | 4步推理，更快 |

### 工作流说明
- `sdxl_1080p_portrait.json` — 使用内置`ImageScale`节点，生成1024x1820后resize到1080x1920
- `wan22_i2v_1080p_8s.json` — Wan2.2 I2V 8秒视频，LoadImage加载SDXL输出的分镜图
- `sdxl_wan22_combined.json` — 组合工作流，一步从文字生成视频

### 16GB显存优化工作流

| 优化项 | 说明 |
|--------|------|
| **SDXL步骤** | 从30步降至20步，cfg从7.0降至6.0 |
| **Wan2.2分辨率** | 从832x480降至640x480，显存占用减少40% |
| **Wan2.2步数** | 从默认降至4步，速度提升5倍 |
| **FP8量化** | 使用Wan2.2 FP8版模型，显存减半 |
| **Batch size** | 始终为1，避免显存溢出 |
| **TeaCache** | 开启缓存加速（ComfyUI-WanVideoWrapper支持） |

---

## 🎙 TTS配音语音

| 角色 | 语音 | 说明 |
|------|------|------|
| 女主 | zh-CN-XiaoxiaoNeural | 温柔女声 |
| 男主 | zh-CN-YunxiNeural | 沉稳男声 |
| 旁白 | zh-CN-YunjianNeural | 浑厚男声 |

支持情感调整（倔强、愤怒、温柔等）通过语速微调实现。

---

## 📊 Pipeline参数与性能

### 本地 5060Ti (16GB) 性能参考

| 步骤 | 工具 | 分辨率 | 单次耗时 |
|------|------|--------|---------|
| 分镜图 | SDXL | 1024x1820 | 12-18秒 |
| 8秒视频 | Wan2.2 I2V (FP8, 4步) | 640x480 | 4-6分钟 |
| TTS配音 | Edge TTS | - | 1-3秒/句 |
| 合成 | FFmpeg | 1080x1920 | 2分钟 |

### 一集成本估算（本地）

| 项目 | 成本 |
|------|------|
| 电费（~200W × 15分钟） | ≈¥0.08 |
| 模型摊销 | ≈¥0.02 |
| **单集约合** | **≈¥0.10** |

---

## 📁 项目结构

```
shortdrama-hotspot/
├── fetch_hotspot.py           # 热点抓取+日报生成
├── pipeline.py                # 一键Pipeline（7步完整流程）
├── config.py                  # 集中配置管理（所有路径/参数/API地址）
├── requirements.txt           # 依赖清单
├── pyproject.toml             # 项目打包配置
├── scripts/
│   ├── generate_script.py     # 剧本生成（含ComfyUI提示词）
│   ├── comfyui_api.py         # ComfyUI API交互（提交/轮询/获取输出）
│   ├── tts_subtitle.py        # TTS配音+字幕生成
│   └── download_models.py     # 模型下载脚本（规划中）
├── utils/
│   ├── __init__.py            # 共享模块入口
│   ├── genre.py               # 题材分类共享模块
│   └── api_helpers.py         # API请求辅助（重试/缓存/日志）
├── templates/
│   ├── genre_templates.json   # 10种题材剧本模板
│   └── comfyui_pipeline_config.json  # Pipeline参数配置
├── workflows/
│   ├── sdxl_1080p_portrait.json       # SDXL 1080P竖屏分镜
│   ├── wan22_i2v_1080p_8s.json        # Wan2.2 I2V 8秒视频
│   ├── sdxl_wan22_combined.json       # SDXL+Wan2.2组合工作流
│   ├── Flux2-Klein-9B-文生图-fp4版_1080p.json  # Flux模型替代
│   └── Wan2.2-14B文生视频-4步_8s.json  # 4步快速版
└── tests/
    ├── __init__.py
    ├── test_genre.py           # 题材分类测试（14用例）
    └── test_config.py          # 配置测试（5用例）
```

---

## 🧩 题材分类

| 题材 | 匹配关键词示例 | 说明 |
|------|---------------|------|
| 霸总 | 总裁、首富、豪门 | 权力型男主 |
| 婚恋 | 婚、妻、闪婚、领证 | 婚姻恋爱关系 |
| 甜宠 | 甜、宠、恋、上瘾 | 甜蜜宠爱向 |
| 逆袭 | 逆袭、巅峰、无敌 | 弱者翻盘崛起 |
| 重生 | 重生、穿越、八零 | 回到过去重新来过 |
| 古装 | 皇、帝、妃、太子 | 古代/宫廷背景 |
| 复仇 | 复仇、恩断 | 报仇雪恨 |
| 悬疑 | 案、侦探、真相 | 案件悬疑推理 |
| 战神 | 战龙、修仙、枭雄 | 战斗/武力型 |
| 逆袭/翻盘 | 离婚、出狱、撤资 | 低谷后翻盘 |

---

## ⏰ 定时自动化

### 配合 cron（Linux/macOS）
```bash
# 每日09:00生成热点日报
0 9 * * * cd /path/to/shortdrama-hotspot && python3 fetch_hotspot.py --report

# 每日09:00热点+剧本
0 9 * * * cd /path/to/shortdrama-hotspot && python3 pipeline.py --auto
```

### 配合 Windows 任务计划程序
```
触发器: 每天 09:00
操作:   python C:\path\to\shortdrama-hotspot\fetch_hotspot.py --report
```

---

## ❓ 常见问题

### Q: 16GB显存够跑Wan2.2吗？
**可以**。必须使用FP8量化版Wan2.2 I2V模型（~14GB），开启 `--lowvram` 模式。分辨率从832x480降至640x480可节省40%显存。

### Q: 热点API不稳定怎么办？
项目内置了重试机制（默认3次，指数退避）和磁盘缓存（默认60分钟过期）。同一小时内重复请求直接读取缓存。

### Q: 剧本太模板化怎么办？
剧本基于10种题材模板+随机组合生成，可通过修改 `templates/genre_templates.json` 自定义。建议AI生成后人工审核调整。

### Q: 支持中文提示词吗？
SDXL工作流使用中译英自动翻译提示词。Wan2.2原生支持中文提示词。

### Q: 如何切换模型？
修改 `templates/comfyui_pipeline_config.json` 中的 `checkpoint` 字段。可替换为其他SDXL微调模型（如RealVisXL、JuggernautXL等）。

### Q: 输出目录在哪里？
默认在项目根目录的 `output/` 下，可通过环境变量 `SHORTDRAMA_OUTPUT_DIR` 修改：
```bash
export SHORTDRAMA_OUTPUT_DIR="/your/custom/path"
```

### Q: FFmpeg报错怎么办？
确保FFmpeg在系统PATH中可用。测试方法：
```bash
ffmpeg -version
```

---

## ⚠️ 注意事项

- 短剧热度榜API为免费第三方接口，可能偶尔不稳定
- SDXL 1024x1820接近SDXL原生训练比例，出图质量最佳
- Wan2.2 I2V-14B模型在480P(832x480)下生成，输出需upscale到1080P
- **16GB显存必须使用Wan2.2 FP8量化版**，FP16版需要24GB+
- 剧本生成基于模板+随机组合，建议人工审核调整
- TTS配音需安装edge-tts：`pip install edge-tts`
- FFmpeg需在系统PATH中可用

---

## 📜 License

MIT

---

## 📝 更新日志

### v4.2 (2026-05-25)
- **新增本地硬件部署指南**：RTX 5060 Ti 16GB + 32GB RAM 详细配置
- **新增16GB显存优化方案**：FP8量化、低分辨率、TeaCache加速
- **新增ComfyUI本地搭建文档**：模型下载、自定义节点、启动参数
- **新增FAQ章节**：覆盖常见问题排查
- **优化文档结构**：快速开始、配置参考、性能对照

### v4.1 (2026-05-23)
- **架构重构**：新增 `config.py`、`utils/genre.py`、`utils/api_helpers.py`
- **Bug修复**：修复 `--comfyui` 参数不生效、硬编码路径移除
- **代码质量**：logging替代print、argparse替代sys.argv、API重试+缓存
- **测试**：新增19个单元测试，全部通过
