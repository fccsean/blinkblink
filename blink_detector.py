"""
眨眼检测器 —— 基于 MediaPipe Face Mesh + Eye Aspect Ratio (EAR)。

核心流程：
1. MediaPipe 提取 468 个人脸关键点 → 取眼部 6 点轮廓
2. 计算 EAR = (上下高度之和) / (2 × 水平宽度)
3. EAR < 阈值 → 判定闭眼 → 记录眨眼时间戳
4. 滑动窗口内统计眨眼频率 → 低于阈值且持续一定时间 → 通知调用方
5. 同时追踪人脸持续存在时间 → 超过阈值 → 久坐提醒
"""

import os
import sys
import time
from collections import deque

import cv2
import numpy as np
from mediapipe import Image, ImageFormat
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import FaceLandmarker, FaceLandmarkerOptions, RunningMode

from config import (
    BLINK_THRESHOLD_EAR,
    LEFT_EYE_INDICES,
    LOW_BLINK_DURATION_SECONDS,
    MIN_BLINKS_FOR_WARNING,
    MONITORING_WINDOW_SECONDS,
    RIGHT_EYE_INDICES,
    SEDENTARY_GRACE_SECONDS,
)

# MediaPipe 模型文件路径：开发时在项目根目录，打包后在 app bundle Resources 中
if getattr(sys, "frozen", False):
    _MODEL_PATH = os.path.join(os.path.dirname(sys.executable), "..", "Resources", "face_landmarker.task")
else:
    _MODEL_PATH = os.path.join(os.path.dirname(__file__), "face_landmarker.task")


def _eye_aspect_ratio(eye_points: np.ndarray) -> float:
    """计算 Eye Aspect Ratio。

    EAR = (|p1-p5| + |p2-p4|) / (2 × |p0-p3|)
    其中 p0=左角, p1=上1, p2=上2, p3=右角, p4=下2, p5=下1

    睁眼 ≈ 0.35–0.45，闭眼 ≈ 0.15–0.20。
    """
    # 垂直方向：上眼睑到下眼睑的两段距离
    v1 = np.linalg.norm(eye_points[1] - eye_points[5])
    v2 = np.linalg.norm(eye_points[2] - eye_points[4])
    # 水平方向：眼角到眼角的距离
    h = np.linalg.norm(eye_points[0] - eye_points[3])
    if h < 1e-7:
        return 1.0  # 极端情况：眼睛宽度为 0，默认视为睁眼
    return (v1 + v2) / (2.0 * h)


def _extract_eye_points(landmarks, indices, frame_w, frame_h):
    """从 MediaPipe 归一化坐标中提取眼部关键点的像素坐标。"""
    points = []
    for idx in indices:
        lm = landmarks[idx]
        points.append((int(lm.x * frame_w), int(lm.y * frame_h)))
    return np.array(points, dtype=np.float64)


class BlinkDetector:
    """基于眼部关键点的眨眼检测器。

    通过 Eye Aspect Ratio (EAR) 判断眼睛开合状态，
    在滑动时间窗口内追踪眨眼频率，低于阈值时发出提醒。
    同时追踪人脸持续存在时间，用于久坐提醒。
    """

    def __init__(self, blink_rate_warning: float = 20.0, sedentary_threshold_seconds: float = 60 * 40):
        """初始化眨眼检测器。

        参数：
            blink_rate_warning: 每分钟眨眼次数低于此阈值时触发提醒（默认 20）
            sedentary_threshold_seconds: 久坐时长阈值，超过后触发提醒（默认 40 分钟）
        """
        self.blink_rate_warning = blink_rate_warning
        self.sedentary_threshold_seconds = sedentary_threshold_seconds

        options = FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=_MODEL_PATH),
            running_mode=RunningMode.IMAGE,  # 逐帧图片模式，非视频流
            num_faces=1,  # 只检测一张人脸，减少计算量
            min_face_detection_confidence=0.5,
            min_tracking_confidence=0.5,
            output_face_blendshapes=False,  # 不需要表情 blendshape，节省计算
            output_facial_transformation_matrixes=False,
        )
        self.landmarker = FaceLandmarker.create_from_options(options)

        # ---- 眨眼相关状态 ----
        self.blink_timestamps: deque[float] = deque()  # 滑动窗口内的眨眼时间戳
        self.eye_closed = False       # 当前是否处于闭眼状态（已消抖）
        self.consecutive_open = 0     # 连续睁眼帧计数
        self.frames_since_start = 0   # 启动以来的帧数（用于抑制启动期误报）
        self._low_rate_since: float | None = None  # 低眨眼率开始的时刻

        # ---- 久坐相关状态 ----
        self._face_present_since: float | None = None  # 人脸开始持续存在的时刻
        self._face_absent_since: float | None = None   # 人脸开始消失的时刻

    # ------------------------------------------------------------------
    # 核心帧处理
    # ------------------------------------------------------------------

    def process_frame(self, frame: np.ndarray):
        """处理一帧画面，返回 (标注后的帧, 状态字典)。

        这是检测器的主入口，每帧调用一次。内部依次完成：
        1. MediaPipe 人脸关键点检测
        2. 人脸存在/消失状态追踪（久坐计时）
        3. EAR 计算 + 眨眼判定
        4. 滑动窗口清理 + 眨眼率统计
        """
        self.frames_since_start += 1
        h, w = frame.shape[:2]

        # BGR → RGB 转换，MediaPipe 要求 RGB 输入
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = Image(image_format=ImageFormat.SRGB, data=rgb)
        result = self.landmarker.detect(mp_image)

        face_detected = bool(result.face_landmarks)
        ear = 1.0
        is_blinking = False
        now = time.time()

        # ---- 久坐计时：追踪人脸持续出现/消失 ----
        if face_detected:
            if self._face_present_since is None:
                self._face_present_since = now  # 人脸刚出现，开始计时
            self._face_absent_since = None
        else:
            if self._face_absent_since is None:
                self._face_absent_since = now  # 人脸刚消失，记录时间
            elif now - self._face_absent_since > SEDENTARY_GRACE_SECONDS:
                # 超过宽限期：确认人已离开，重置所有状态
                self._face_present_since = None
                self.reset_blinks()
                self._face_absent_since = None  # 置空防止后续每帧重复 reset

        # ---- 眨眼检测 ----
        if face_detected:
            landmarks = result.face_landmarks[0]

            # 提取左右眼关键点并计算 EAR
            left_pts = _extract_eye_points(landmarks, LEFT_EYE_INDICES, w, h)
            right_pts = _extract_eye_points(landmarks, RIGHT_EYE_INDICES, w, h)
            left_ear = _eye_aspect_ratio(left_pts)
            right_ear = _eye_aspect_ratio(right_pts)
            ear = (left_ear + right_ear) / 2.0

            # 任一只眼睛 EAR 低于阈值即判定为闭眼
            # 用"或"而非双眼平均再比较，以捕获单眼/不完全眨眼
            either_closed = (
                left_ear < BLINK_THRESHOLD_EAR
                or right_ear < BLINK_THRESHOLD_EAR
            )

            if either_closed:
                self.consecutive_open = 0
                if not self.eye_closed:
                    # 睁眼 → 闭眼 的跳变：记录一次眨眼
                    self.eye_closed = True
                    self.blink_timestamps.append(time.time())
                    is_blinking = True
            else:
                self.consecutive_open += 1
                # 连续 2 帧睁眼才确认脱离闭眼态（消抖，防止单帧误判）
                if self.consecutive_open >= 2:
                    self.eye_closed = False

            # 在画面上绘制眼部关键点（绿色圆点）
            for pt in left_pts:
                cv2.circle(frame, tuple(pt.astype(int)), 3, (0, 255, 0), -1)
            for pt in right_pts:
                cv2.circle(frame, tuple(pt.astype(int)), 3, (0, 255, 0), -1)

        # ---- 清理过期眨眼并统计 ----
        self._prune_old_blinks()

        blink_count = len(self.blink_timestamps)
        elapsed = self._elapsed_seconds()
        blink_rate = (blink_count / max(elapsed, 1)) * 60.0  # 换算为 次/分钟

        status = {
            "blink_rate": blink_rate,
            "total_blinks": blink_count,
            "is_blinking": is_blinking,
            "face_detected": face_detected,
            "ear": ear,
            "sedentary_seconds": self.sedentary_seconds,
            "blink_rate_warning": self.blink_rate_warning,
            "sedentary_threshold_seconds": self.sedentary_threshold_seconds,
        }
        return frame, status

    # ------------------------------------------------------------------
    # 提醒判断
    # ------------------------------------------------------------------

    def should_warn(self, blink_rate: float) -> bool:
        """判断是否应触发眨眼提醒。

        条件：
        1. 已处理至少 60 帧（给检测器预热时间）
        2. 窗口内至少有 MIN_BLINKS_FOR_WARNING 次眨眼
        3. 低眨眼率状态持续超过 LOW_BLINK_DURATION_SECONDS 秒
        """
        now = time.time()
        if self.frames_since_start < 60:
            return False
        if len(self.blink_timestamps) < MIN_BLINKS_FOR_WARNING:
            return False

        # 用迟滞逻辑避免瞬时波动：只有连续低于阈值才触发
        if blink_rate < self.blink_rate_warning:
            if self._low_rate_since is None:
                self._low_rate_since = now  # 记录低速率起始时间
            return (now - self._low_rate_since) >= LOW_BLINK_DURATION_SECONDS
        else:
            self._low_rate_since = None  # 速率恢复正常，重置追踪
            return False

    @property
    def sedentary_seconds(self) -> float:
        """当前持续检测到人脸的秒数，未检测到则返回 0。"""
        if self._face_present_since is None:
            return 0.0
        return time.time() - self._face_present_since

    def should_warn_sedentary(self) -> bool:
        """人脸持续出现超过阈值时返回 True。"""
        if self.sedentary_seconds < self.sedentary_threshold_seconds:
            return False
        return True

    # ------------------------------------------------------------------
    # 状态重置
    # ------------------------------------------------------------------

    def reset_sedentary(self):
        """重置久坐计时（提醒发送后由主循环调用）。"""
        self._face_present_since = None
        self._face_absent_since = None

    def reset_blinks(self):
        """只重置眨眼相关状态，不影响久坐计时（眨眼提醒发送后调用）。"""
        self.blink_timestamps.clear()
        self.eye_closed = False
        self.consecutive_open = 0
        self.frames_since_start = 0
        self._low_rate_since = None

    def reset(self):
        """完全重置，包括眨眼和久坐状态（用户手动按键触发）。"""
        self.reset_blinks()
        self._face_present_since = None
        self._face_absent_since = None

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _prune_old_blinks(self):
        """清理滑动窗口外的过期眨眼记录。

        窗口大小由 MONITORING_WINDOW_SECONDS 定义。
        使用双端队列，每次只清理头部过期项，O(k) 其中 k 为过期数量。
        """
        cutoff = time.time() - MONITORING_WINDOW_SECONDS
        while self.blink_timestamps and self.blink_timestamps[0] < cutoff:
            self.blink_timestamps.popleft()

    def _elapsed_seconds(self) -> float:
        """滑动窗口的实际时间跨度。

        从最早一次眨眼到当前时刻。若无眨眼记录则返回 1.0（避免除零）。
        """
        if not self.blink_timestamps:
            return 1.0
        return time.time() - self.blink_timestamps[0]

    # ------------------------------------------------------------------
    # 资源管理
    # ------------------------------------------------------------------

    def close(self):
        """释放 MediaPipe 资源。"""
        self.landmarker.close()

    def __del__(self):
        """析构时确保资源释放。"""
        if hasattr(self, "landmarker"):
            self.landmarker.close()
