#!/usr/bin/env python3
"""配置模块单元测试"""

import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config, config


class TestConfig:
    """配置模块测试"""

    def test_project_root_exists(self):
        """项目根目录存在"""
        assert config.PROJECT_ROOT.exists()

    def test_templates_dir_exists(self):
        """模板目录存在"""
        assert config.TEMPLATES_DIR.exists()

    def test_workflows_dir_exists(self):
        """工作流目录存在"""
        assert config.WORKFLOWS_DIR.exists()

    def test_api_urls_not_empty(self):
        """API URL不为空"""
        assert config.SHORTDRAMA_API
        assert config.DOUYIN_HOT_API

    def test_ensure_dirs(self):
        """目录创建功能"""
        cfg = Config()
        cfg.ensure_dirs()
        assert cfg.OUTPUT_DIR.exists()

    def test_default_python_exe(self):
        """Python解释器路径不为空"""
        assert config.PYTHON_EXE

    def test_cost_per_hour_positive(self):
        """每小时成本为正"""
        assert config.COST_PER_HOUR > 0


if __name__ == "__main__":
    test = TestConfig()
    methods = [m for m in dir(test) if m.startswith("test_")]
    passed = 0
    failed = 0
    for method in methods:
        try:
            getattr(test, method)()
            print(f"  ✓ {method}")
            passed += 1
        except AssertionError as e:
            print(f"  ✗ {method}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ {method}: 异常 {e}")
            failed += 1
    print(f"\n测试结果: {passed} 通过, {failed} 失败")
