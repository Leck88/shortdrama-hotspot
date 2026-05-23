#!/usr/bin/env python3
"""题材分类模块单元测试"""

import sys
import os

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.genre import classify_genre, GENRE_MAP


class TestClassifyGenre:
    """题材分类测试"""

    def test_ba_zong(self):
        """霸总类"""
        assert "霸总" in classify_genre("总裁的秘密")
        assert "霸总" in classify_genre("首富爱上我")
        assert "霸总" in classify_genre("豪门风云")

    def test_hun_lian(self):
        """婚恋类"""
        assert "婚恋" in classify_genre("闪婚总裁")
        assert "婚恋" in classify_genre("宠妻日常")
        assert "婚恋" in classify_genre("妻子的秘密")

    def test_tian_chong(self):
        """甜宠类"""
        assert "甜宠" in classify_genre("甜心宝贝")
        assert "甜宠" in classify_genre("只对她温柔")

    def test_ni_xi(self):
        """逆袭类"""
        assert "逆袭" in classify_genre("逆袭之路")
        assert "逆袭" in classify_genre("无敌战将")

    def test_chong_sheng(self):
        """重生类"""
        assert "重生" in classify_genre("重生之巅峰")
        assert "重生" in classify_genre("穿越八零")
        assert "重生" in classify_genre("前世今生")

    def test_gu_zhuang(self):
        """古装类"""
        assert "古装" in classify_genre("太子妃传")
        assert "古装" in classify_genre("后宫如懿")

    def test_fu_chou(self):
        """复仇类"""
        assert "复仇" in classify_genre("复仇女王")
        assert "复仇" in classify_genre("恩断义绝")

    def test_xuan_yi(self):
        """悬疑类"""
        assert "悬疑" in classify_genre("迷案追踪")
        assert "悬疑" in classify_genre("真相大白")

    def test_zhan_shen(self):
        """战神类"""
        assert "战神" in classify_genre("战神归来")
        assert "战神" in classify_genre("战龙天下")

    def test_multi_genre(self):
        """多题材叠加"""
        result = classify_genre("离婚后闪婚总裁")
        assert "婚恋" in result
        assert "逆袭/翻盘" in result

    def test_other(self):
        """无法分类 -> 其他"""
        assert classify_genre("普通故事") == ["其他"]
        assert classify_genre("日记") == ["其他"]

    def test_genre_map_completeness(self):
        """验证题材映射表完整性"""
        assert len(GENRE_MAP) == 10
        for genre, keywords in GENRE_MAP.items():
            assert len(keywords) > 0, f"题材 {genre} 没有关键词"


if __name__ == "__main__":
    # 简单运行测试
    test = TestClassifyGenre()
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
