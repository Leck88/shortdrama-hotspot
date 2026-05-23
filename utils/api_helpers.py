#!/usr/bin/env python3
"""
API 请求辅助模块 (API Request Helpers)

提供带重试、缓存和日志的 HTTP 请求函数。
"""

import json
import logging
import time
import urllib.request
import urllib.error
from pathlib import Path

logger = logging.getLogger("shortdrama.api")


def fetch_json_with_retry(
    url: str,
    timeout: int = 15,
    max_retries: int = 3,
    retry_delay: float = 2.0,
    cache_dir: str | None = None,
    cache_expire_minutes: int = 60,
) -> dict | None:
    """
    带重试机制的 JSON API 请求

    特性：
    - 自动重试（指数退避）
    - 可选的磁盘缓存（避免重复请求）
    - 结构化日志

    参数：
        url: API 接口地址
        timeout: 单次请求超时（秒）
        max_retries: 最大重试次数
        retry_delay: 首次重试延迟（秒），后续指数退避
        cache_dir: 缓存目录路径，None 则不缓存
        cache_expire_minutes: 缓存过期时间（分钟）

    返回：
        解析后的 JSON 字典，失败返回 None
    """
    # 尝试读取缓存
    if cache_dir:
        cache_key = url.replace("https://", "").replace("http://", "").replace("/", "_").replace("?", "_")
        cache_path = Path(cache_dir) / f"{cache_key}.json"
        if cache_path.exists():
            cache_age = time.time() - cache_path.stat().st_mtime
            if cache_age < cache_expire_minutes * 60:
                logger.info(f"命中缓存: {url} (缓存年龄 {cache_age/60:.1f} 分钟)")
                try:
                    with open(cache_path, "r", encoding="utf-8") as f:
                        return json.load(f)
                except (json.JSONDecodeError, OSError):
                    logger.warning(f"缓存文件损坏，重新请求: {cache_path}")

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (shortdrama-hotspot/4.1)",
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                logger.info(f"请求成功: {url} (第 {attempt} 次)")
                # 写入缓存
                if cache_dir:
                    Path(cache_dir).mkdir(parents=True, exist_ok=True)
                    try:
                        with open(cache_path, "w", encoding="utf-8") as f:
                            json.dump(data, f, ensure_ascii=False, indent=2)
                    except OSError as e:
                        logger.warning(f"缓存写入失败: {e}")
                return data
        except urllib.error.HTTPError as e:
            last_error = e
            logger.warning(f"HTTP 错误 {e.code}: {url} (第 {attempt}/{max_retries} 次)")
        except urllib.error.URLError as e:
            last_error = e
            logger.warning(f"URL 错误 {e.reason}: {url} (第 {attempt}/{max_retries} 次)")
        except (TimeoutError, OSError) as e:
            last_error = e
            logger.warning(f"请求超时/网络错误: {url} (第 {attempt}/{max_retries} 次)")
        except json.JSONDecodeError as e:
            last_error = e
            logger.error(f"JSON 解析失败: {url} - {e}")
            return None  # 解析失败不重试

        if attempt < max_retries:
            delay = retry_delay * (2 ** (attempt - 1))  # 指数退避
            logger.info(f"等待 {delay:.1f}s 后重试...")
            time.sleep(delay)

    logger.error(f"请求最终失败: {url} (已重试 {max_retries} 次) - {last_error}")
    return None
