# 护眼助手 (Eye Protection Monitor)

基于摄像头的实时眨眼监测工具。检测眨眼频率，当长时间不眨眼时发送 macOS 通知提醒，同时追踪久坐时间，帮助预防数码眼疲劳。

## 功能

- 通过摄像头实时检测眨眼，视频窗口左上角显示眨眼率、EAR（眼睛长宽比）、眨眼次数、久坐时长
- 眨眼率持续低于设定阈值时，发送 macOS 系统通知提醒休息眼睛（默认 20 次/分钟，可通过设置对话框或命令行参数调整）
- 人脸持续被检测到超过 40 分钟时，发送久坐提醒
- 支持窗口模式（实时预览，按键 `q` 退出 / `r` 重置）和后台模式（`-b` 纯命令行运行）
- 眨眼和久坐使用独立冷却期，互不干扰

## 实现原理

**脸部关键点**：使用 MediaPipe Face Landmarker 模型提取面部 478 个关键点，取左右眼各 6 个轮廓点计算 Eye Aspect Ratio (EAR)。

**眨眼检测**：EAR = 眼睛垂直高度 ÷ 水平宽度。睁眼时 ≈ 0.35–0.45，闭眼时 ≈ 0.15–0.20。任一只眼睛 EAR 低于 0.20 即判定为闭眼（捕获不完全眨眼），通过追踪闭眼-睁眼状态切换来计数。连续 2 帧睁眼才确认脱离闭眼态，防止单帧误判。

**频率追踪**：在 120 秒滑动窗口内统计眨眼次数，换算为每分钟眨眼率。低于设定阈值（默认 20 次/分钟）且持续 10 秒以上才触发提醒（避免瞬时波动误报）。窗口内至少累积 10 次眨眼才做判断（防止启动初期数据不足误报）。

**久坐追踪**：追踪人脸持续出现的时长，超过 40 分钟触发起身活动提醒。人脸短暂消失 5 秒内不计（防止转头、喝水等动作误重置）。

**通知**：通过 osascript 调用 macOS 原生通知系统。

## 安装与运行

```bash
# 安装依赖
pip install -r requirements.txt

# 下载 MediaPipe Face Landmarker 模型
# 从 https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker 下载
# 放到项目根目录命名为 face_landmarker.task

# 窗口模式运行
python3 main.py

# 后台模式运行
python3 main.py -b
```

### 打包为 macOS 应用

```bash
python3 setup.py py2app
```

## 配置

`config.py` 中可调整以下参数（眨眼率阈值和久坐时长已改为启动时通过 UI 或命令行设置）：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `BLINK_THRESHOLD_EAR` | 0.20 | EAR 眨眼判定阈值 |
| `MONITORING_WINDOW_SECONDS` | 120 | 滑动窗口大小（秒） |
| `MIN_BLINKS_FOR_WARNING` | 10 | 窗口内最少眨眼次数，低于此数不触发 |
| `LOW_BLINK_DURATION_SECONDS` | 10 | 低眨眼率需持续多久才触发通知（秒） |
| `NOTIFICATION_COOLDOWN_SECONDS` | 60 | 两次眨眼提醒最小间隔（秒） |
| `SEDENTARY_COOLDOWN_SECONDS` | 2400 | 两次久坐提醒最小间隔（秒） |
| `SEDENTARY_GRACE_SECONDS` | 5 | 人脸短暂消失宽限期（秒） |
| `CAMERA_WIDTH` | 2560 | 摄像头采集分辨率宽度 |
| `FRAME_SKIP` | 1 | 跳帧间隔（1 = 逐帧检测） |

以下参数通过启动时的设置对话框或命令行参数配置：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| 眨眼率阈值 | 20 次/分钟 | 低于此值触发眨眼提醒 |
| 久坐时长 | 40 分钟 | 久坐超过此时间触发提醒 |

```bash
# 命令行指定
python3 main.py --blink-rate 15 --sedentary-minutes 30

# 窗口模式弹出设置对话框
python3 main.py
```
