"""
macOS 系统通知发送模块。

通过 osascript 调用 AppleScript display notification 发送系统通知。
内置独立的冷却时间控制，防止眨眼提醒和久坐提醒互相干扰。
"""

import subprocess
import time

from config import NOTIFICATION_COOLDOWN_SECONDS, SEDENTARY_COOLDOWN_SECONDS

# 眨眼和久坐使用独立的"上次通知时间"，防止一种提醒阻断另一种
_last_blink_notification = 0.0
_last_sedentary_notification = 0.0


def _send(title: str, message: str, cooldown: float, last_key: str) -> bool:
    """发送 macOS 系统通知，内置冷却控制。

    参数：
        title: 通知标题
        message: 通知正文
        cooldown: 两次通知最小间隔（秒）
        last_key: "blink" 或 "sedentary"，用于查询/更新对应冷却计时器

    返回：
        True 表示通知已发送，False 表示因冷却被抑制。
    """
    global _last_blink_notification, _last_sedentary_notification

    last_map = {
        "blink": _last_blink_notification,
        "sedentary": _last_sedentary_notification,
    }
    now = time.time()
    # 冷却检查：距上次通知不足 cooldown 秒则跳过
    if now - last_map[last_key] < cooldown:
        return False

    # 更新冷却计时器
    if last_key == "blink":
        _last_blink_notification = now
    else:
        _last_sedentary_notification = now

    # AppleScript 字符串需要转义反斜杠和双引号
    escaped_message = message.replace("\\", "\\\\").replace('"', '\\"')
    escaped_title = title.replace("\\", "\\\\").replace('"', '\\"')
    script = f'display notification "{escaped_message}" with title "{escaped_title}"'
    subprocess.run(["osascript", "-e", script], capture_output=True)
    return True


def send_notification(title: str, message: str) -> bool:
    """发送眨眼提醒通知，使用 blink 冷却时间。"""
    return _send(title, message, NOTIFICATION_COOLDOWN_SECONDS, "blink")


def send_sedentary_notification(title: str, message: str) -> bool:
    """发送久坐提醒通知，使用独立的 sedentary 冷却时间。"""
    return _send(title, message, SEDENTARY_COOLDOWN_SECONDS, "sedentary")
