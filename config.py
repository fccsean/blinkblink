# 眨眼检测阈值：EAR（眼睛长宽比）低于此值判定为闭眼
# 正常睁眼 ≈ 0.35–0.45，闭眼 ≈ 0.15–0.20，0.20 是较敏感的阈值
BLINK_THRESHOLD_EAR = 0.20

# 计算眨眼频率的滑动时间窗口（秒），窗口越长越平滑，但响应越慢
MONITORING_WINDOW_SECONDS = 120

# 窗口内至少需检测到的眨眼次数，低于此数不发警告（防止启动初期误报）
MIN_BLINKS_FOR_WARNING = 10

# 低眨眼率需持续的最低秒数，避免瞬时波动触发误报
LOW_BLINK_DURATION_SECONDS = 10

# 两次眨眼提醒之间的最小间隔（秒），防止连续骚扰
NOTIFICATION_COOLDOWN_SECONDS = 60

# 摄像头设备索引（0 = 内置 FaceTime 摄像头）
CAMERA_INDEX = 0

# 摄像头采集分辨率宽度，高度自动按 16:9 计算
CAMERA_WIDTH = 2560

# 预览窗口显示宽度，高度自动按比例计算
DISPLAY_WIDTH = 2560

# 跳帧间隔：每 N 帧运行一次人脸检测，1 = 逐帧检测，2 = 隔帧
# 越小越灵敏但 CPU 占用越高
FRAME_SKIP = 1

# 两次久坐提醒之间的最小间隔（秒）
SEDENTARY_COOLDOWN_SECONDS = 60 * 40

# 人脸短暂消失的宽限期（秒），在此时间内不会重置久坐计时
# 防止用户转头/喝水等短暂离开画面导致计时中断
SEDENTARY_GRACE_SECONDS = 5

# MediaPipe Face Mesh 眼睛关键点索引（6 点眼轮廓）
# 左眼：[左角, 上1, 上2, 右角, 下2, 下1]
LEFT_EYE_INDICES = [33, 160, 158, 133, 153, 144]
# 右眼：[左角, 上1, 上2, 右角, 下2, 下1]
RIGHT_EYE_INDICES = [362, 385, 387, 263, 373, 380]

# 通知消息模板
BLINK_WARNING_TITLE = "Eye Protection"
BLINK_WARNING_MESSAGE = "Blink rate: {rate:.0f}/min. Remember to blink! Damon宝宝,注意休息眼睛"
SEDENTARY_WARNING_TITLE = "Sedentary Reminder"
SEDENTARY_WARNING_MESSAGE = "You've been sitting for a while. Time to stand up and walk around!"

# 默认用户设置值（供 settings 持久化模块和 main.py 回退使用）
DEFAULT_BLINK_RATE = 20.0
DEFAULT_SEDENTARY_SECONDS = 40 * 60
