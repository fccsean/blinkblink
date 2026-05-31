"""测试 JSON 设置持久化模块。"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import json
import pytest
from settings import load_settings, save_settings, SETTINGS_PATH


@pytest.fixture
def clean_settings():
    """确保测试前后 SETTINGS_PATH 不存在，并保存原始文件。"""
    backed_up = None
    if os.path.exists(SETTINGS_PATH):
        with open(SETTINGS_PATH, "r") as f:
            backed_up = f.read()
        os.remove(SETTINGS_PATH)
    yield
    if os.path.exists(SETTINGS_PATH):
        os.remove(SETTINGS_PATH)
    if backed_up is not None:
        with open(SETTINGS_PATH, "w") as f:
            f.write(backed_up)


def test_load_defaults(clean_settings):
    """无 JSON 文件时 load_settings() 返回默认值"""
    s = load_settings()
    assert s["blink_rate"] == 20.0
    assert s["sedentary_seconds"] == 2400


def test_save_and_load(clean_settings):
    """保存后加载返回相同值"""
    save_settings(15.0, 1800)
    s = load_settings()
    assert s["blink_rate"] == 15.0
    assert s["sedentary_seconds"] == 1800


def test_corrupted_json(clean_settings):
    """JSON 文件格式损坏时返回默认值（不崩溃）"""
    with open(SETTINGS_PATH, "w") as f:
        f.write("this is not valid json {{{")
    s = load_settings()
    assert s["blink_rate"] == 20.0
    assert s["sedentary_seconds"] == 2400
