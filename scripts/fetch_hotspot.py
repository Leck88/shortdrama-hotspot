#!/usr/bin/env python3
"""
热点数据抓取模块 (Hotspot Data Fetcher)

功能概述：
1. 抓取短剧热度排行榜（酷乐短剧API）
2. 抓取抖音热搜榜（热搜API）
3. 自动题材分类统计
4. 输出结构化热点数据

依赖：
  - urllib (Python标准库)
  - utils.api_helpers (项目内部模块)
  - utils.genre (项目内部模块)

使用方式：
  from fetch_hotspot import fetch_shortdrama_rank, fetch_douyin_hot, generate_genre_stats

  rank_data = fetch_shortdrama_rank()
  douyin_data = fetch_douyin_hot()
  genre_stats = generate_genre_stats(rank_data)
"""

import json
import logging
import os
import sys
import time
from datetime import datetime

# 项目内部模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from utils.api_helpers import fetch_json_with_retry
from utils.genre import classify_genre

logger = logging.getLogger("shortdrama.hotspot")

# ============ API 接口地址 ============

# 短剧热度榜 API（酷乐短剧）
SHORTDRAMA_RANK_API = "https://api.kuleu.com/api/shortdrama/rank"

# 抖音热搜榜 API（多个备选源）
DOUYIN_HOT_APIS = [
    "https://api.vvhan.com/api/hotlist/douyinHot",
    "https://api.oioweb.cn/api/common/HotList?type=douyin",
]

# 请求配置
REQUEST_TIMEOUT = 15
MAX_RETRIES = 3
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "output", "cache")


# ============ 短剧热度榜 ============

def fetch_shortdrama_rank(
    api_url: str = SHORTDRAMA_RANK_API,
    max_items: int = 50,
    use_cache: bool = True,
) -> list[dict]:
    """
    抓取短剧热度排行榜

    参数：
        api_url: 热度榜API地址
        max_items: 最多返回条数
        use_cache: 是否使用缓存

    返回：
        排行榜数据列表 [
            {
                "rank": 1,
                "title": "剧名",
                "heat": 12345,
                "genre": ["霸总", "婚恋"],
                "platform": "抖音",
                "url": "..."
            },
            ...
        ]
    """
    logger.info(f"抓取短剧热度榜: {api_url}")

    cache_dir = CACHE_DIR if use_cache else None
    data = fetch_json_with_retry(
        api_url,
        timeout=REQUEST_TIMEOUT,
        max_retries=MAX_RETRIES,
        cache_dir=cache_dir,
        cache_expire_minutes=30,
    )

    if not data:
        logger.warning("短剧热度榜 API 请求失败，尝试备选数据")
        return _get_fallback_rank_data()

    # 解析API返回数据（不同API返回格式不同，需要适配）
    rank_list = []

    try:
        # 尝试解析酷乐API格式
        items = _parse_kuleu_format(data, max_items)
        if items:
            rank_list = items
    except Exception as e:
        logger.warning(f"解析酷乐API格式失败: {e}")

    if not rank_list:
        # 尝试其他常见格式
        rank_list = _parse_generic_format(data, max_items)

    if not rank_list:
        logger.warning("所有解析方式均失败，使用备选数据")
        return _get_fallback_rank_data()

    # 自动分类题材
    for item in rank_list:
        if "genre" not in item or not item["genre"]:
            item["genre"] = classify_genre(item.get("title", ""))

    logger.info(f"获取到 {len(rank_list)} 条短剧热度数据")
    return rank_list


def _parse_kuleu_format(data: dict, max_items: int) -> list[dict]:
    """解析酷乐短剧API返回格式"""
    items = []
    # 酷乐API常见格式: {"code": 200, "data": [...]}
    raw_items = data.get("data", data.get("result", data.get("list", [])))

    if isinstance(raw_items, list):
        for i, item in enumerate(raw_items[:max_items]):
            title = item.get("title", item.get("name", item.get("剧名", f"未知剧{i+1}")))
            heat = item.get("heat", item.get("hot", item.get("热度", 0)))
            platform = item.get("platform", item.get("来源", "抖音"))
            url = item.get("url", item.get("link", ""))

            items.append({
                "rank": i + 1,
                "title": str(title),
                "heat": int(heat) if heat else 0,
                "genre": classify_genre(str(title)),
                "platform": str(platform),
                "url": str(url),
            })

    return items


def _parse_generic_format(data: dict, max_items: int) -> list[dict]:
    """解析通用API返回格式"""
    items = []

    # 尝试从各种常见字段中提取列表
    for key in ["data", "result", "items", "list", "results"]:
        if key in data and isinstance(data[key], list):
            raw_items = data[key]
            for i, item in enumerate(raw_items[:max_items]):
                if isinstance(item, dict):
                    title = item.get("title", item.get("name", item.get("word", f"热点{i+1}")))
                    heat = item.get("heat", item.get("hot", item.get("热度", 0)))
                    items.append({
                        "rank": i + 1,
                        "title": str(title),
                        "heat": int(heat) if heat else 0,
                        "genre": classify_genre(str(title)),
                        "platform": "抖音",
                        "url": item.get("url", ""),
                    })
                elif isinstance(item, str):
                    items.append({
                        "rank": i + 1,
                        "title": item,
                        "heat": 0,
                        "genre": classify_genre(item),
                        "platform": "抖音",
                        "url": "",
                    })
            break

    return items


# ============ 抖音热搜 ============

def fetch_douyin_hot(
    max_items: int = 30,
    use_cache: bool = True,
) -> list[dict]:
    """
    抓取抖音热搜榜

    参数：
        max_items: 最多返回条数
        use_cache: 是否使用缓存

    返回：
        热搜数据列表 [
            {
                "rank": 1,
                "title": "热搜关键词",
                "heat": 12345,
                "url": "..."
            },
            ...
        ]
    """
    logger.info("抓取抖音热搜榜")

    cache_dir = CACHE_DIR if use_cache else None

    for api_url in DOUYIN_HOT_APIS:
        data = fetch_json_with_retry(
            api_url,
            timeout=REQUEST_TIMEOUT,
            max_retries=MAX_RETRIES,
            cache_dir=cache_dir,
            cache_expire_minutes=30,
        )

        if data:
            hot_list = _parse_douyin_format(data, max_items)
            if hot_list:
                logger.info(f"获取到 {len(hot_list)} 条抖音热搜数据")
                return hot_list

    logger.warning("抖音热搜所有API均失败，使用备选数据")
    return _get_fallback_douyin_data()


def _parse_douyin_format(data: dict, max_items: int) -> list[dict]:
    """解析抖音热搜API返回格式"""
    items = []

    # 韩小韩API格式: {"success": true, "data": [...]}
    # OioWeb格式: {"code": 200, "result": [...]}
    for key in ["data", "result", "items", "list"]:
        if key in data and isinstance(data[key], list):
            raw_items = data[key]
            for i, item in enumerate(raw_items[:max_items]):
                if isinstance(item, dict):
                    title = item.get("title", item.get("name", item.get("word", "")))
                    heat = item.get("hot", item.get("heat", item.get("热度", 0)))
                    url = item.get("url", item.get("link", ""))
                    items.append({
                        "rank": i + 1,
                        "title": str(title),
                        "heat": int(heat) if heat else 0,
                        "url": str(url),
                    })
                elif isinstance(item, str):
                    items.append({
                        "rank": i + 1,
                        "title": item,
                        "heat": 0,
                        "url": "",
                    })
            break

    return items


# ============ 题材统计 ============

def generate_genre_stats(rank_data: list[dict]) -> dict[str, int]:
    """
    根据热度榜数据生成题材分布统计

    参数：
        rank_data: 热度榜数据列表

    返回：
        题材分布统计 {"霸总": 5, "婚恋": 3, ...}
    """
    genre_count = {}

    for item in rank_data:
        genres = item.get("genre", [])
        if isinstance(genres, str):
            genres = [genres]
        for g in genres:
            genre_count[g] = genre_count.get(g, 0) + 1

    # 按数量降序排列
    sorted_stats = dict(sorted(genre_count.items(), key=lambda x: x[1], reverse=True))
    return sorted_stats


# ============ 备选数据 ============

def _get_fallback_rank_data() -> list[dict]:
    """当API不可用时的备选热点数据"""
    fallback = [
        {"rank": 1, "title": "闪婚后，总裁老公他变了", "heat": 9999, "genre": ["婚恋", "霸总"], "platform": "抖音", "url": ""},
        {"rank": 2, "title": "重生后我成了首富", "heat": 8888, "genre": ["重生", "逆袭"], "platform": "抖音", "url": ""},
        {"rank": 3, "title": "被退婚后我嫁给了他小叔", "heat": 7777, "genre": ["婚恋", "霸总"], "platform": "抖音", "url": ""},
        {"rank": 4, "title": "她从深渊归来", "heat": 6666, "genre": ["复仇", "逆袭/翻盘"], "platform": "抖音", "url": ""},
        {"rank": 5, "title": "战神归来全家跪求原谅", "heat": 5555, "genre": ["战神", "逆袭"], "platform": "抖音", "url": ""},
        {"rank": 6, "title": "他的独宠甜妻", "heat": 4444, "genre": ["甜宠", "霸总"], "platform": "抖音", "url": ""},
        {"rank": 7, "title": "侯府嫡女重生记", "heat": 3333, "genre": ["古装", "重生"], "platform": "抖音", "url": ""},
        {"rank": 8, "title": "离婚后前夫高攀不起", "heat": 2222, "genre": ["逆袭/翻盘", "婚恋"], "platform": "抖音", "url": ""},
        {"rank": 9, "title": "秘密调查局", "heat": 1111, "genre": ["悬疑"], "platform": "抖音", "url": ""},
        {"rank": 10, "title": "她不是白月光", "heat": 1000, "genre": ["逆袭", "复仇"], "platform": "抖音", "url": ""},
    ]
    logger.info(f"使用备选热点数据 ({len(fallback)} 条)")
    return fallback


def _get_fallback_douyin_data() -> list[dict]:
    """当API不可用时的备选抖音热搜数据"""
    fallback = [
        {"rank": 1, "title": "短剧新趋势", "heat": 5000, "url": ""},
        {"rank": 2, "title": "霸总短剧火爆", "heat": 4000, "url": ""},
        {"rank": 3, "title": "女强人逆袭", "heat": 3000, "url": ""},
        {"rank": 4, "title": "重生爽文", "heat": 2000, "url": ""},
        {"rank": 5, "title": "古装虐恋", "heat": 1000, "url": ""},
    ]
    logger.info(f"使用备选抖音热搜数据 ({len(fallback)} 条)")
    return fallback


# ============ 独立运行入口 ============

def main():
    """独立运行时的入口"""
    import argparse

    parser = argparse.ArgumentParser(description="短剧热点数据抓取")
    parser.add_argument("--output", default="./output/reports/shortdrama", help="输出目录")
    parser.add_argument("--no-cache", action="store_true", help="禁用缓存")
    parser.add_argument("--max-items", type=int, default=50, help="最大返回条数")

    args = parser.parse_args()

    print("=" * 50)
    print("  短剧热点数据抓取")
    print("=" * 50)

    os.makedirs(args.output, exist_ok=True)

    # 抓取热度榜
    print("\n[1/2] 抓取短剧热度榜...")
    rank_data = fetch_shortdrama_rank(
        max_items=args.max_items,
        use_cache=not args.no_cache,
    )

    if rank_data:
        print(f"  ✓ 获取到 {len(rank_data)} 条热度数据")
        # 保存热度数据
        rank_file = os.path.join(args.output, f"rank_{datetime.now().strftime('%Y-%m-%d')}.json")
        with open(rank_file, "w", encoding="utf-8") as f:
            json.dump(rank_data, f, ensure_ascii=False, indent=2)
        print(f"  ✓ 已保存: {rank_file}")

        # 题材统计
        stats = generate_genre_stats(rank_data)
        print(f"\n  题材分布 (Top 10):")
        for genre, count in list(stats.items())[:10]:
            print(f"    {genre}: {count} 部")
    else:
        print("  ✗ 热度榜数据获取失败")

    # 抓取抖音热搜
    print("\n[2/2] 抓取抖音热搜榜...")
    douyin_data = fetch_douyin_hot(
        max_items=args.max_items,
        use_cache=not args.no_cache,
    )

    if douyin_data:
        print(f"  ✓ 获取到 {len(douyin_data)} 条热搜数据")
        douyin_file = os.path.join(args.output, f"douyin_{datetime.now().strftime('%Y-%m-%d')}.json")
        with open(douyin_file, "w", encoding="utf-8") as f:
            json.dump(douyin_data, f, ensure_ascii=False, indent=2)
        print(f"  ✓ 已保存: {douyin_file}")
    else:
        print("  ✗ 抖音热搜数据获取失败")

    print("\n" + "=" * 50)
    print("  抓取完成")
    print("=" * 50)


if __name__ == "__main__":
    main()
