"""
py2app 打包配置。

构建命令：python setup.py py2app
推荐使用 build.sh 一键构建（含代码签名修复）。
"""

import os
import sys

from setuptools import setup

APP = ["main.py"]
APP_NAME = "Eye Protection.app"
PY_VERSION = f"python{sys.version_info.major}.{sys.version_info.minor}"

MEDIAPIPE_DYLIB_TARGET = os.path.abspath(
    os.path.join(
        "dist",
        APP_NAME,
        "Contents",
        "Resources",
        "lib",
        PY_VERSION,
        "mediapipe",
        "tasks",
        "c",
        "libmediapipe.dylib",
    )
)

# 需要打入 app bundle 的数据文件（模型文件放在 app 根目录）
DATA_FILES = [
    ("", ["face_landmarker.task"]),
]

OPTIONS = {
    "argv_emulation": False,  # 不模拟命令行参数（纯 GUI 应用）
    "packages": ["mediapipe", "cv2", "numpy"],
    "includes": [
        "blink_detector",
        "config",
        "notifier",
    ],
    "excludes": ["matplotlib", "PIL", "Pillow"],
    "dylib_excludes": [MEDIAPIPE_DYLIB_TARGET],
    "semi_standalone": True,  # 跳过 Mach-O header 重写，避免 mediapipe dylib 签名损坏
    "plist": {
        "CFBundleName": "Eye Protection",
        "CFBundleDisplayName": "Eye Protection",
        "CFBundleIdentifier": "com.eyeprotection.app",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0",
        # macOS 摄像头权限声明（必须，否则无法访问摄像头）
        "NSCameraUsageDescription": "需要访问摄像头来检测眨眼频率，保护您的眼睛健康。",
        "NSMicrophoneUsageDescription": "",
    },
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
