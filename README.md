# shortdrama-hotspot

短剧热点监控工具 —— 每日自动抓取短剧热度排行榜、抖音短剧相关热搜，生成结构化日报。

## 功能

- 获取短剧热度排行榜 Top30（数据源：酷乐API）
- 获取抖音热搜并智能筛选短剧/影视相关词条
- 自动分类 10 种题材（婚恋、霸总、甜宠、逆袭、战神、古装等）
- 生成 Markdown 格式结构化日报
- 支持命令行参数和定时自动化运行

## 数据源

| 数据源 | 接口 | 说明 |
|--------|------|------|
| 短剧热度榜 | `https://api.kuleu.com/api/shortdramarank` | 免费，无需 Key，每日更新 |
| 抖音热搜 | `https://v2.xxapi.cn/api/douyinhot` | 免费，无需 Key，实时更新 |

## 安装

无需安装依赖，使用 Python 3 标准库（`urllib`, `json`）。

```bash
git clone https://github.com/Leck88/shortdrama-hotspot.git
cd shortdrama-hotspot
```

## 使用

### 快速查看

```bash
python fetch_hotspot.py
```

输出控制台摘要 + JSON 格式数据。

### 生成日报文件

```bash
python fetch_hotspot.py --report --output "D:/视频生产/reports/shortdrama"
```

生成 `短剧热点日报_YYYY-MM-DD.md` 到指定目录。

### 仅获取热度榜

```bash
python fetch_hotspot.py --rank-only
```

### 参数说明

| 参数 | 说明 |
|------|------|
| `--report` | 生成 Markdown 日报文件 |
| `--output <dir>` | 指定报告输出目录（默认 `D:\视频生产\reports\shortdrama`） |
| `--rank-only` | 仅获取短剧热度榜，跳过抖音热搜 |

## 日报格式

```markdown
# 短剧热点日报 - 2026年05月22日

## 🔥 短剧热度榜 Top15
| 排名 | 剧名 | 热度 |
|------|------|------|
| 1 | xxx | xxxw |

## 📱 抖音短剧相关热搜
## 📈 题材分布
## 💡 选题参考
```

## 定时自动化

配合 WorkBuddy 的自动化功能，可设置每日定时执行：

```bash
# 每日 09:00 自动执行
python fetch_hotspot.py --report --output "D:/视频生产/reports/shortdrama"
```

也可以配合 cron / 任务计划程序使用。

## 题材分类

脚本根据剧名关键词自动分类，支持以下题材：

婚恋、霸总、甜宠、逆袭、重生、古装、复仇、悬疑、战神、逆袭/翻盘

未匹配的归入"其他"类别。

## License

MIT
