# shortdrama-hotspot

**短剧热点监控 + 仿制剧本 + ComfyUI一键生成 + TTS配音+字幕** —— 从热点发现到成品视频的完整闭环。

> 适用于短剧创作者、选题策划、行业研究者，快速掌握短剧市场热点并一键生成AI短剧。

## 功能

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

## 数据源

| 数据源 | 接口地址 | 说明 |
|--------|----------|------|
| 短剧热度榜 | `https://api.kuleu.com/api/shortdramarank` | 免费，无需Key，每日更新30条排名 |
| 抖音热搜 | `https://v2.xxapi.cn/api/douyinhot` | 免费，无需Key，实时更新 |

## 安装

```bash
git clone https://github.com/Leck88/shortdrama-hotspot.git
cd shortdrama-hotspot

# 安装TTS依赖（可选，配音功能需要）
pip install edge-tts

# FFmpeg需在系统PATH中可用
```

核心功能无需任何第三方依赖，使用Python 3标准库即可运行。

## 项目结构

```
shortdrama-hotspot/
├── fetch_hotspot.py           # 热点抓取+日报生成
├── pipeline.py                # 一键Pipeline v3.0（7步完整流程）
├── scripts/
│   ├── generate_script.py     # 剧本生成（含ComfyUI提示词）
│   ├── comfyui_api.py         # ComfyUI API交互（提交/轮询/获取输出）
│   └── tts_subtitle.py        # TTS配音+字幕生成
├── templates/
│   ├── genre_templates.json   # 10种题材剧本模板
│   └── comfyui_pipeline_config.json  # Pipeline参数配置
└── workflows/
    ├── sdxl_1080p_portrait.json       # SDXL 1080P竖屏分镜（ImageScale节点）
    ├── wan22_i2v_1080p_8s.json        # Wan2.2 I2V 8秒视频
    └── sdxl_wan22_combined.json       # SDXL+Wan2.2一步到位组合工作流
```

## 使用方式

### 查看热点
```bash
python fetch_hotspot.py
```

### 生成日报
```bash
python fetch_hotspot.py --report --output "D:/视频生产/reports/shortdrama"
```

### 生成剧本（含ComfyUI配置）
```bash
python fetch_hotspot.py --script --comfyui           # 自动选最热题材
python fetch_hotspot.py --script --genre "霸总" --comfyui  # 指定题材
python fetch_hotspot.py --script --batch --comfyui   # 批量生成5个
```

### 一键Pipeline
```bash
python pipeline.py --auto                         # 抓热点→剧本→ComfyUI配置
python pipeline.py --auto --genre "婚恋"          # 指定题材
python pipeline.py --auto --run-comfyui           # +调用ComfyUI API生图生视频
python pipeline.py --auto --run-comfyui --tts     # +TTS配音+字幕
python pipeline.py --cost-estimate                # 查看成本估算
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

## ComfyUI配置

### 硬件和成本
- **GPU**: RTX 4080S 32GB
- **云算力**: ¥1.8/小时 (AutoDL)
- **一集成本**: 约¥1.95（含TTS配音，~65分钟）

### Pipeline参数
| 步骤 | 工具 | 分辨率 | 单次耗时 | 单次成本 |
|------|------|--------|---------|---------|
| 分镜图 | SDXL | 1024x1820→1080x1920 | 8-12秒 | ~0.005元 |
| 8秒视频 | Wan2.2 I2V | 832x480→upscale1080P | 3-5分钟 | ~0.15元 |
| TTS配音 | Edge TTS | - | 1-3秒/句 | ~0.001元 |
| 合成 | FFmpeg | 1080x1920 | 2分钟 | ~0.06元 |

### 成本估算
| 集数 | 预估时间 | 预估成本 |
|:----:|----------|---------:|
| 1集 | ~1.1小时 | ¥1.95 |
| 10集 | ~10.8小时 | ¥19.50 |
| 30集 | ~32.5小时 | ¥58.50 |
| 100集 | ~108.3小时 | ¥195.00 |

### 工作流说明
- `sdxl_1080p_portrait.json` — 使用内置`ImageScale`节点（替代非内置ImageResize），生成1024x1820后resize到1080x1920
- `wan22_i2v_1080p_8s.json` — Wan2.2 I2V 8秒视频，LoadImage加载SDXL输出的分镜图
- `sdxl_wan22_combined.json` — 组合工作流，一步从文字生成视频

## 题材分类

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

## TTS配音语音

| 角色 | 语音 | 说明 |
|------|------|------|
| 女主 | zh-CN-XiaoxiaoNeural | 温柔女声 |
| 男主 | zh-CN-YunxiNeural | 沉稳男声 |
| 旁白 | zh-CN-YunjianNeural | 浑厚男声 |

支持情感调整（倔强、愤怒、温柔等）通过语速微调实现。

## 定时自动化

### 配合 WorkBuddy
每日09:00自动执行，生成热点日报。

### 配合 cron（Linux/macOS）
```bash
0 9 * * * cd /path/to/shortdrama-hotspot && python3 fetch_hotspot.py --report
```

## 注意事项

- 短剧热度榜API为免费第三方接口，可能偶尔不稳定
- SDXL 1024x1820接近SDXL原生训练比例，出图质量最佳
- Wan2.2 I2V-14B模型在480P(832x480)下生成，输出需upscale到1080P
- ComfyUI工作流已修复使用内置`ImageScale`节点
- 剧本生成基于模板+随机组合，需人工审核调整
- TTS配音需安装edge-tts (`pip install edge-tts`)

## License

MIT


## v4.1 更新日志 (2026-05-23)

### 🏗️ 架构重构
- **新增 `config.py`**：集中配置管理，所有路径、API地址、参数统一维护，支持环境变量覆盖
- **新增 `utils/genre.py`**：题材分类共享模块，消除 `fetch_hotspot.py` 和 `generate_script.py` 中的重复 `classify_genre` 函数
- **新增 `utils/api_helpers.py`**：API 请求辅助模块，带重试（指数退避）、磁盘缓存、结构化日志
- **新增 `requirements.txt` + `pyproject.toml`**：规范依赖管理和项目打包

### 🐛 Bug 修复
- **修复 `--comfyui` 参数不生效**：`fetch_hotspot.py` 中 `--comfyui` 参数被解析但从未传递给剧本生成函数
- **修复 `submit_workflows_from_dir` 参数不匹配**：`pipeline.py` 调用时传了 `suffix` 参数，但函数定义使用 `pattern`
- **移除硬编码路径**：`D:\视频生产\...` 和 `C:\Users\H\.workbuddy\...` 等硬编码路径全部改为通过 config 管理

### 🔧 代码质量
- 使用 `logging` 模块替代 `print`，支持日志级别控制
- 使用 `argparse` 替代手动 `sys.argv` 解析，提供 `--help` 和参数校验
- API 请求增加重试机制（指数退避，默认3次），免费接口不再容易因超时失败
- 增加磁盘缓存，同一小时内的重复 API 请求直接读取缓存

### 🧪 测试
- **新增 `tests/test_genre.py`**：题材分类单元测试（14个用例，覆盖全部10种题材）
- **新增 `tests/test_config.py`**：配置模块单元测试（5个用例）
- 所有 19 个测试通过

### 📁 新增文件
```
config.py                  # 集中配置管理
utils/__init__.py          # 共享模块入口
utils/genre.py             # 题材分类
utils/api_helpers.py       # API请求辅助
requirements.txt           # 依赖清单
pyproject.toml             # 项目打包配置
tests/__init__.py          # 测试入口
tests/test_genre.py        # 题材测试
tests/test_config.py       # 配置测试
```
