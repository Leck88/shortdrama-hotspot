#!/usr/bin/env python3
"""
集中配置管理模块 (Centralized Configuration)

所有路径、API地址、参数等统一在此管理，支持环境变量覆盖。
硬编码路径已移除，改为相对路径 + 环境变量。

使用方式：
    from config import Config
    cfg = Config()
    print(cfg.output_dir)
"""

import os
import sys
from pathlib import Path


class Config:
    """全局配置，支持环境变量覆盖"""

    # ============ 项目路径 ============
    PROJECT_ROOT = Path(__file__).resolve().parent

    # 输出目录：优先读环境变量，否则用项目根目录下的 output/
    OUTPUT_DIR = Path(os.environ.get(
        "SHORTDRAMA_OUTPUT_DIR",
        str(PROJECT_ROOT / "output")
    ))
    REPORT_DIR = OUTPUT_DIR / "reports" / "shortdrama"
    SCRIPT_DIR = OUTPUT_DIR / "scripts"
    VIDEO_DIR = OUTPUT_DIR / "videos"
    TTS_DIR = OUTPUT_DIR / "tts"
    SUBTITLE_DIR = OUTPUT_DIR / "subtitles"

    # 模板和工作流目录（项目内置）
    TEMPLATES_DIR = PROJECT_ROOT / "templates"
    WORKFLOWS_DIR = PROJECT_ROOT / "workflows"
    SCRIPTS_PKG_DIR = PROJECT_ROOT / "scripts"

    # ============ API 配置 ============
    SHORTDRAMA_API = os.environ.get(
        "SHORTDRAMA_API_URL",
        "https://api.kuleu.com/api/shortdramarank"
    )
    DOUYIN_HOT_API = os.environ.get(
        "DOUYIN_HOT_API_URL",
        "https://v2.xxapi.cn/api/douyinhot"
    )

    # API 请求配置
    API_TIMEOUT = int(os.environ.get("SHORTDRAMA_API_TIMEOUT", "15"))
    API_MAX_RETRIES = int(os.environ.get("SHORTDRAMA_API_RETRIES", "3"))
    API_RETRY_DELAY = float(os.environ.get("SHORTDRAMA_API_RETRY_DELAY", "2.0"))

    # ============ ComfyUI 配置 ============
    COMFYUI_API_URL = os.environ.get(
        "COMFYUI_API_URL",
        "http://127.0.0.1:8188"
    )

    # ============ 成本参数 ============
    COST_PER_HOUR = float(os.environ.get("SHORTDRAMA_COST_PER_HOUR", "1.8"))
    SDXL_TIME_PER_IMAGE_S = 10
    WAN22_TIME_PER_VIDEO_S = 240
    FFMPEG_TIME_S = 120
    TTS_TIME_S = 30

    # ============ Python 解释器（TTS用） ============
    PYTHON_EXE = os.environ.get(
        "SHORTDRAMA_PYTHON",
        sys.executable  # 默认使用当前 Python 解释器
    )

    # ============ 日志配置 ============
    LOG_LEVEL = os.environ.get("SHORTDRAMA_LOG_LEVEL", "INFO")
    LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    # ============ 数据缓存 ============
    CACHE_DIR = OUTPUT_DIR / ".cache"
    CACHE_EXPIRE_MINUTES = int(os.environ.get("SHORTDRAMA_CACHE_EXPIRE", "60"))

    def ensure_dirs(self):
        """确保所有输出目录存在"""
        for d in [self.OUTPUT_DIR, self.REPORT_DIR, self.SCRIPT_DIR,
                  self.VIDEO_DIR, self.TTS_DIR, self.SUBTITLE_DIR,
                  self.CACHE_DIR]:
            d.mkdir(parents=True, exist_ok=True)


# 全局单例
config = Config()
