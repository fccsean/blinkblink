"""用户设置持久化模块 —— JSON 文件读写。

设置文件：~/.eyeprotection.json
格式：{"blink_rate": 20.0, "sedentary_seconds": 2400}
"""
import json
import os
import logging
from config import DEFAULT_BLINK_RATE, DEFAULT_SEDENTARY_SECONDS

logger = logging.getLogger(__name__)

SETTINGS_PATH = os.path.join(os.path.expanduser("~"), ".eyeprotection.json")


def load_settings():
    """加载持久化设置，返回 dict。

    文件不存在或 JSON 损坏时返回默认值，不抛异常。
    """
    defaults = {
        "blink_rate": DEFAULT_BLINK_RATE,
        "sedentary_seconds": DEFAULT_SEDENTARY_SECONDS,
    }
    if not os.path.exists(SETTINGS_PATH):
        return defaults
    try:
        with open(SETTINGS_PATH, "r") as f:
            data = json.load(f)
        for key, val in defaults.items():
            if key not in data:
                data[key] = val
        return data
    except (json.JSONDecodeError, IOError) as e:
        logger.warning("Failed to load settings: %s, using defaults", e)
        return defaults


def save_settings(blink_rate, sedentary_seconds):
    """保存设置到 JSON 文件。"""
    data = {
        "blink_rate": float(blink_rate),
        "sedentary_seconds": int(sedentary_seconds),
    }
    try:
        with open(SETTINGS_PATH, "w") as f:
            json.dump(data, f, indent=2)
    except IOError as e:
        logger.warning("Failed to save settings: %s", e)
