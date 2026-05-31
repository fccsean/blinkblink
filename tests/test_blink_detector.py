"""测试 Eye Aspect Ratio (EAR) 计算函数。"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
import pytest
from blink_detector import _eye_aspect_ratio


def test_eye_aspect_ratio_open():
    """模拟睁眼坐标：EAR 应在 0.35–0.45 范围"""
    # 典型睁眼：水平宽 80，垂直开口约 28 → EAR ≈ 0.35
    # p0=左角(10,100), p1=上1(30,86), p2=上2(70,86),
    # p3=右角(90,100), p4=下2(70,114), p5=下1(30,114)
    eye_points = np.array(
        [
            [10.0, 100.0],  # p0: 左角
            [30.0, 86.0],  # p1: 上1
            [70.0, 86.0],  # p2: 上2
            [90.0, 100.0],  # p3: 右角
            [70.0, 114.0],  # p4: 下2
            [30.0, 114.0],  # p5: 下1
        ],
        dtype=np.float64,
    )
    ear = _eye_aspect_ratio(eye_points)
    # 睁眼 EAR 应 > 0.30
    assert ear > 0.30, f"Expected open eye EAR > 0.30, got {ear:.3f}"
    # 睁眼 EAR 应 < 0.60（安全上限）
    assert ear < 0.60, f"Expected open eye EAR < 0.60, got {ear:.3f}"


def test_eye_aspect_ratio_closed():
    """模拟闭眼坐标：EAR 应 < 0.20"""
    # 模拟闭眼：垂直距离非常小（几乎闭合）
    # p1-p5 和 p2-p4 的垂直差距仅 2px → v1=v2=2, h=20 → EAR=0.10
    eye_points = np.array(
        [
            [30.0, 100.0],  # p0: 左角
            [35.0, 99.0],  # p1: 上1（几乎在眼角线上）
            [45.0, 99.0],  # p2: 上2
            [50.0, 100.0],  # p3: 右角
            [45.0, 101.0],  # p4: 下2（几乎在眼角线上）
            [35.0, 101.0],  # p5: 下1
        ],
        dtype=np.float64,
    )
    ear = _eye_aspect_ratio(eye_points)
    assert ear < 0.20, f"Expected closed eye EAR < 0.20, got {ear:.3f}"


def test_eye_aspect_ratio_zero_width():
    """极端情况：眼睛宽度为 0 时返回 1.0（安全默认值，不崩溃）"""
    # 所有点在同一位置 → 水平距离 h=0
    eye_points = np.array(
        [
            [0.0, 0.0],
            [0.0, 0.0],
            [0.0, 0.0],
            [0.0, 0.0],
            [0.0, 0.0],
            [0.0, 0.0],
        ],
        dtype=np.float64,
    )
    ear = _eye_aspect_ratio(eye_points)
    assert ear == 1.0, f"Expected EAR=1.0 for zero-width eye, got {ear:.3f}"
