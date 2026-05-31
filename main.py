"""
护眼助手 —— 基于摄像头的眨眼监测工具。

检测眨眼频率，当长时间不眨眼时发送 macOS 通知提醒。
同时追踪久坐时间，超时后提醒起身活动。
支持窗口模式（实时预览）和后台模式（纯命令行运行）。
"""

import argparse
import logging
import os
import signal
import sys
import time

import cv2

from blink_detector import BlinkDetector
from config import (
    CAMERA_INDEX, CAMERA_WIDTH, DISPLAY_WIDTH, FRAME_SKIP,
    BLINK_WARNING_TITLE, BLINK_WARNING_MESSAGE,
    SEDENTARY_WARNING_TITLE, SEDENTARY_WARNING_MESSAGE,
    DEFAULT_BLINK_RATE, DEFAULT_SEDENTARY_SECONDS,
)
from settings import load_settings, save_settings, SETTINGS_PATH
from notifier import send_notification, send_sedentary_notification

# 日志输出到 ~/Library/Logs/EyeProtection/app.log
_LOG_DIR = os.path.join(os.path.expanduser("~"), "Library", "Logs", "EyeProtection")
os.makedirs(_LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(_LOG_DIR, "app.log")),
        logging.StreamHandler(sys.stderr),
    ],
)
logger = logging.getLogger(__name__)


def _show_settings_dialog(default_blink_rate: float, default_sedentary_minutes: int):
    """弹出设置对话框，让用户输入眨眼率阈值和久坐时长。

    如果 tkinter 不可用（例如在无 GUI 环境中打包运行），直接返回默认值。
    返回 (blink_rate, sedentary_seconds)。
    """
    try:
        import tkinter as tk
    except ImportError:
        logger.warning("tkinter not available, using default settings")
        return default_blink_rate, default_sedentary_minutes * 60

    root = tk.Tk()
    root.title("Eye Protection Settings")
    root.resizable(False, False)

    frame = tk.Frame(root, padx=20, pady=15)
    frame.pack()

    tk.Label(frame, text="每分钟眨眼次数阈值（低于此值触发提醒）：").grid(row=0, column=0, sticky="w", pady=(0, 2))
    blink_var = tk.StringVar(value=str(int(default_blink_rate)))
    blink_entry = tk.Entry(frame, textvariable=blink_var, width=8, justify="center")
    blink_entry.grid(row=1, column=0, sticky="w", pady=(0, 12))

    tk.Label(frame, text="久坐提醒时长（分钟）：").grid(row=2, column=0, sticky="w", pady=(0, 2))
    sed_var = tk.StringVar(value=str(default_sedentary_minutes))
    sed_entry = tk.Entry(frame, textvariable=sed_var, width=8, justify="center")
    sed_entry.grid(row=3, column=0, sticky="w", pady=(0, 12))

    result = {"blink_rate": default_blink_rate, "sedentary_seconds": default_sedentary_minutes * 60}

    def on_ok():
        try:
            result["blink_rate"] = float(blink_var.get())
        except ValueError:
            pass
        try:
            result["sedentary_seconds"] = int(sed_var.get()) * 60
        except ValueError:
            pass
        root.destroy()

    def on_cancel():
        root.destroy()

    btn_frame = tk.Frame(frame)
    btn_frame.grid(row=4, column=0, sticky="e", pady=(4, 0))
    tk.Button(btn_frame, text="Cancel", width=8, command=on_cancel).pack(side=tk.LEFT, padx=(0, 8))
    tk.Button(btn_frame, text="OK", width=8, command=on_ok).pack(side=tk.LEFT)

    root.update_idletasks()
    w, h = root.winfo_width(), root.winfo_height()
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")
    blink_entry.focus_set()
    blink_entry.selection_range(0, tk.END)

    root.mainloop()
    return result["blink_rate"], result["sedentary_seconds"]


def main():
    parser = argparse.ArgumentParser(description="Eye Protection Blink Monitor")
    parser.add_argument(
        "-b", "--background", action="store_true",
        help="后台模式，不显示预览窗口",
    )
    parser.add_argument(
        "--blink-rate", type=float, default=None,
        help="每分钟眨眼次数阈值，低于此值触发提醒（默认 20）",
    )
    parser.add_argument(
        "--sedentary-minutes", type=int, default=None,
        help="久坐提醒时长（分钟）（默认 40）",
    )
    args = parser.parse_args()

    settings = load_settings()
    has_saved = os.path.exists(SETTINGS_PATH)

    blink_rate = args.blink_rate
    sedentary_seconds = args.sedentary_minutes * 60 if args.sedentary_minutes is not None else None

    if blink_rate is not None and sedentary_seconds is not None:
        logger.info("Settings from CLI: blink_rate=%.0f/min, sedentary=%ds",
                    blink_rate, sedentary_seconds)
    else:
        if blink_rate is None:
            if has_saved:
                blink_rate = settings["blink_rate"]
                logger.info("Settings from JSON: blink_rate=%.0f/min", blink_rate)
            elif not args.background:
                blink_rate, sedentary_seconds = _show_settings_dialog(
                    DEFAULT_BLINK_RATE, DEFAULT_SEDENTARY_SECONDS // 60,
                )
                logger.info("Settings from dialog: blink_rate=%.0f/min, sedentary=%ds",
                            blink_rate, sedentary_seconds)
            else:
                blink_rate = DEFAULT_BLINK_RATE

        if sedentary_seconds is None:
            if has_saved:
                sedentary_seconds = settings["sedentary_seconds"]
                logger.info("Settings from JSON: sedentary=%ds", sedentary_seconds)
            elif not args.background:
                blink_rate, sedentary_seconds = _show_settings_dialog(
                    blink_rate, DEFAULT_SEDENTARY_SECONDS // 60,
                )
                logger.info("Settings from dialog: blink_rate=%.0f/min, sedentary=%ds",
                            blink_rate, sedentary_seconds)
            else:
                sedentary_seconds = DEFAULT_SEDENTARY_SECONDS

    # 打开摄像头，分辨率由 config 控制（2560×1440，16:9）
    cap = cv2.VideoCapture(CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_WIDTH * 9 // 16)
    if not cap.isOpened():
        print(f"Error: Could not open camera (index {CAMERA_INDEX})")
        print("Grant camera permission in: System Settings > Privacy & Security > Camera")
        sys.exit(1)

    if not args.background:
        cv2.namedWindow("Eye Protection Monitor", cv2.WINDOW_NORMAL)

    # 延迟初始化检测器：等拿到第一帧后再创建（获取实际帧尺寸）
    detector = None
    frame_count = 0
    last_status_text = ""
    running = True

    def on_sigint(sig, frame):
        nonlocal running
        running = False
    signal.signal(signal.SIGINT, on_sigint)

    mode = "background" if args.background else "window"
    logger.info("Eye Protection Monitor starting (%s mode)", mode)
    print(f"Eye Protection Monitor started ({mode} mode).", flush=True)
    if not args.background:
        print("Press 'q' to quit, 'r' to reset blink history.\n")
    else:
        print("Press Ctrl+C to quit.\n", flush=True)

    try:
        while running:
            ret, frame = cap.read()
            if not ret:
                if frame_count == 0:
                    # 摄像头刚启动可能需要预热，最多等 5 秒
                    deadline = time.time() + 5
                    while not ret and time.time() < deadline:
                        time.sleep(0.1)
                        ret, frame = cap.read()
                    if not ret:
                        print("Error: Could not read frame from camera")
                        break
                else:
                    print("Error: Lost camera connection")
                    break

            # 延迟初始化检测器（拿到第一帧后才能确定画面尺寸）
            if detector is None:
                detector = BlinkDetector(
                    blink_rate_warning=blink_rate,
                    sedentary_threshold_seconds=sedentary_seconds,
                )
                if not args.background:
                    h, w = frame.shape[:2]
                    scale = DISPLAY_WIDTH / w
                    cv2.resizeWindow("Eye Protection Monitor", DISPLAY_WIDTH, int(h * scale))
                save_settings(blink_rate, sedentary_seconds)

            frame = cv2.flip(frame, 1)  # 水平翻转，产生镜像效果
            frame_count += 1

            # 跳帧处理：降低 CPU 占用
            if frame_count % FRAME_SKIP == 0:
                # ---- 核心调用：检测器处理一帧 ----
                frame, status = detector.process_frame(frame)
                last_status_text = _build_overlay_text(status)

                # 后台模式每 90 帧打印一次状态到终端
                if args.background and frame_count % 90 == 0:
                    sed_str = ""
                    if status.get("sedentary_seconds", 0) > 0:
                        mm, ss = divmod(int(status["sedentary_seconds"]), 60)
                        sed_str = f" | Sitting: {mm}:{ss:02d}"
                    print(f"Rate: {status['blink_rate']:.0f}/min | "
                          f"Blinks: {status['total_blinks']} | "
                          f"EAR: {status['ear']:.3f}{sed_str}", flush=True)

                # ---- 眨眼提醒管线 ----
                # 检测眨眼率过低 → 发送通知 → 重置眨眼计数器（不动久坐计时）
                if detector.should_warn(status["blink_rate"]):
                    sent = send_notification(
                        BLINK_WARNING_TITLE,
                        BLINK_WARNING_MESSAGE.format(rate=status['blink_rate']),
                    )
                    if sent:
                        detector.reset_blinks()

                # ---- 久坐提醒管线 ----
                # 检测人脸持续存在超过阈值 → 发送通知 → 重置久坐计时
                if detector.should_warn_sedentary():
                    sent = send_sedentary_notification(
                        SEDENTARY_WARNING_TITLE,
                        SEDENTARY_WARNING_MESSAGE,
                    )
                    if sent:
                        detector.reset_sedentary()

            # 窗口模式：绘制状态叠加层并显示
            if not args.background:
                _draw_overlay(frame, last_status_text)
                h, w = frame.shape[:2]
                scale = DISPLAY_WIDTH / w
                display = cv2.resize(frame, (DISPLAY_WIDTH, int(h * scale)))
                cv2.imshow("Eye Protection Monitor", display)

                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                elif key == ord("r"):
                    detector.reset()  # 手动完全重置
                    print("Blink history reset.")

    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        if not args.background:
            cv2.destroyAllWindows()
        if detector:
            detector.close()
        print("Monitor stopped.", flush=True)
        logger.info("Monitor stopped normally")


# ------------------------------------------------------------------
# UI 辅助函数
# ------------------------------------------------------------------

def _build_overlay_text(status: dict) -> str:
    face = "Yes" if status["face_detected"] else "No"
    blink = "BLINK" if status["is_blinking"] else ""
    blink_warn = status.get("blink_rate_warning", 0)
    sed_min = status.get("sedentary_threshold_seconds", 0) // 60
    lines = [
        f"Face: {face}",
        f"EAR: {status['ear']:.3f}",
        f"Blink Rate: {status['blink_rate']:.1f}/min  (warn <{blink_warn:.0f})",
        f"Blink Count: {status['total_blinks']}",
    ]
    if status.get("sedentary_seconds", 0) > 0:
        mm, ss = divmod(int(status["sedentary_seconds"]), 60)
        lines.append(f"Sitting: {mm}:{ss:02d}  (limit {sed_min}min)")
    else:
        lines.append(f"Sit Limit: {sed_min}min")
    if blink:
        lines.append(blink)
    return "\n".join(lines)


def _draw_overlay(frame, text: str):
    """在画面左上角绘制半透明黑色背景的状态信息叠加层。"""
    if not text:
        return

    lines = text.split("\n")
    line_count = len(lines)
    box_w, box_h = 500, 38 + line_count * 36

    # 在半透明层上绘制黑色矩形背景
    overlay = frame.copy()
    cv2.rectangle(overlay, (5, 5), (box_w, box_h), (0, 0, 0), -1)
    frame[:] = cv2.addWeighted(frame, 0.55, overlay, 0.45, 0)

    # 逐行绘制文字，不同状态用不同颜色
    for i, line in enumerate(lines):
        color = (0, 255, 0)       # 默认绿色
        if line.startswith("Face: No"):
            color = (0, 0, 255)    # 无人脸 → 红色
        elif line.startswith("BLINK"):
            color = (0, 255, 255)  # 眨眼事件 → 黄色
        cv2.putText(frame, line, (18, 38 + i * 36),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("Fatal error")
        raise
