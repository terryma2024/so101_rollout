# SO101 机械臂环境配置手册

基于 [LeRobot](https://github.com/huggingface/lerobot) 的 SO101 主从臂（leader / follower）遥操作环境。

## 1. 环境概览

| 项目 | 版本 / 说明 |
|---|---|
| 系统 | Ubuntu (Linux x86_64) |
| Python | 3.12（由 uv 管理的 `.venv`） |
| LeRobot | 0.6.1，`lerobot[feetech,viz]`（viz 提供 rerun 可视化） |
| PyTorch | 2.11.0 + CUDA 13.0（RTX 5060 Ti 可用） |
| 舵机 | Feetech STS3215 × 6 / 臂，波特率 1 Mbps，ID 1–6 |
| 摄像头 | 从臂手腕 `wrist`、侧面 `side`，均为 icSpring USB 摄像头，640×480，按 20 fps 使用 |

## 2. 硬件连接

两只手臂通过 USB 串口连接（CH343 芯片，`1a86:55d3`）。使用 `/dev/serial/by-id/` 路径，重新插拔后不会变化：

| 手臂 | 序列号 | 串口路径 | 当前设备 |
|---|---|---|---|
| 主臂 leader | `5CE5113682` | `/dev/serial/by-id/usb-1a86_USB_Single_Serial_5CE5113682-if00` | `/dev/ttyACM0` |
| 从臂 follower | `5CE5122459` | `/dev/serial/by-id/usb-1a86_USB_Single_Serial_5CE5122459-if00` | `/dev/ttyACM1` |

> `ttyACM0/1` 编号可能随插拔顺序改变，脚本统一使用 by-id 路径。

从臂手腕摄像头：

| 项目 | 值 |
|---|---|
| 型号 | icSpring camera（USB `32e6:9005`，USB 2.0） |
| 设备路径 | `/dev/v4l/by-id/usb-icSpring_icspring_camera-video-index0`（当前为 `/dev/video0`；`/dev/video1` 是元数据通道，不出图） |
| 格式 | 仅支持 640×480 YUYV |
| 帧率 | 标称 30 fps，实测最高约 22.6 fps（与曝光无关），因此配置为 20 fps |

> 录制数据集时帧率建议也用 20 fps，按 30 fps 录制会有约 1/4 的重复帧。

侧面摄像头：

| 项目 | 值 |
|---|---|
| 型号 | icSpring camera（USB `32e6:9221`，序列号 `202404160005`，USB 2.0） |
| 设备路径 | `/dev/v4l/by-id/usb-icSpring_icspring_camera_202404160005-video-index0`（当前为 `/dev/video2`；`/dev/video3` 是元数据通道） |
| 格式 | MJPG 320×240 至 1920×1080；YUYV 仅 640×480。配置为 640×480 MJPG（省 USB 带宽） |
| 帧率 | 标称 30 fps，各分辨率实测均约 20 fps（与曝光无关），配置为 20 fps；与手腕摄像头同时运行互不影响 |
| 镜头 | 广角，画面边缘有畸变 |

关节编号：

| ID | 关节 | 说明 |
|---|---|---|
| 1 | shoulder_pan | 底座旋转 |
| 2 | shoulder_lift | 大臂俯仰 |
| 3 | elbow_flex | 小臂俯仰 |
| 4 | wrist_flex | 手腕俯仰 |
| 5 | wrist_roll | 手腕旋转 |
| 6 | gripper | 夹爪 |

## 3. 安装

### 3.1 系统准备

```bash
# 串口权限：当前用户需在 dialout 组（加入后需重新登录）
sudo usermod -aG dialout $USER

# 录制数据集需要 ffmpeg
sudo apt install ffmpeg

# uv
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 3.2 Python 环境

本项目已用 uv 初始化，依赖锁定在 `uv.lock`，直接同步即可：

```bash
cd ~/Projects/so101_test
uv sync
```

从零创建时使用的命令（供参考）：

```bash
uv init --python 3.12 --name so101-test --no-workspace
uv add "lerobot[feetech,viz]"
```

### 3.3 验证

```bash
uv run python -c "import torch, lerobot; print(torch.__version__, torch.cuda.is_available())"
ls -l /dev/serial/by-id/
```

## 4. 文件说明

| 文件 | 作用 |
|---|---|
| `arms.env` | 主从臂串口路径和 ID（`my_leader` / `my_follower`），手腕和侧面摄像头路径和帧率 |
| `calibrate_follower.sh` | 校准从臂 |
| `calibrate_leader.sh` | 校准主臂 |
| `teleop.sh` | 启动遥操作（主臂控制从臂），同时用 rerun 显示手腕、侧面摄像头画面和关节数据 |
| `teleop_viz.py` | `lerobot-teleoperate` 的包装：图像按摄像头帧率（20 Hz）发给 rerun，去掉重复帧（两个摄像头约 4 MB/s，原版约 12 MB/s），控制频率不变 |
| `read_pose.py` | 只读对比两臂当前关节角度（不上扭矩，手臂不会动） |

## 5. 使用流程

> 校准和遥操作需要键盘交互，请在独立终端中运行（不要用 Claude Code 的 `!` 前缀）。

### 5.1 识别串口（换电脑或换线后）

```bash
uv run lerobot-find-port
```

按提示拔掉某只手臂的 USB，即可确认其串口；然后更新 `arms.env`。

### 5.2 校准

```bash
./calibrate_follower.sh
./calibrate_leader.sh
```

每只手臂的步骤：

1. **摆到中间位置后按 Enter。** 每个关节放在其活动范围的大约正中间（无需精确）：
   底座朝正前方，大臂竖直向上，小臂与大臂约 90° 向前伸，手腕伸直，夹爪半开。
   参考官方图片：<https://huggingface.co/docs/lerobot/so101>（Calibrate 一节）。
2. **逐个关节慢慢转到两端极限**，屏幕显示每个关节的 MIN / MAX。
3. 全部转完后**再按 Enter** 保存。

主臂和从臂的中间姿态要尽量一致。

校准文件位置（本机设置了 `HF_HOME=/data/models/huggingface`）：

```
/data/models/huggingface/lerobot/calibration/robots/so_follower/my_follower.json
/data/models/huggingface/lerobot/calibration/teleoperators/so_leader/my_leader.json
```

未设置 `HF_HOME` 时默认在 `~/.cache/huggingface/lerobot/calibration/`。

正常的校准结果：

- 1–4 号关节 `range_min`/`range_max` 大致以 2047 为中心，跨度约 2000–2600；
- 5 号 `wrist_roll` 为整圈舵机，固定为 `0`–`4095`；
- 6 号夹爪范围约 1300–1500，主从臂不同不影响使用（按 0–100% 映射）。

### 5.3 校准检查

把两只手臂摆成相同姿势，然后：

```bash
uv run read_pose.py
```

各关节 `diff` 在 ±2° 左右即说明两臂校准一致。若姿势相同但某关节相差很大，重新校准对应手臂。

### 5.4 遥操作

```bash
./teleop.sh
```

启动后会用 rerun 显示手腕、侧面摄像头画面和各关节数据（`--display_data=true`），脚本自动选择查看方式：

- **在本机桌面运行**：直接弹出 rerun 窗口。
- **通过 SSH 运行（没有图形界面）**：数据发送到你自己电脑上的原生 rerun 查看器（地址见 `arms.env` 的 `RERUN_VIEWER_HOST`，当前为 MacBook `100.84.127.95`）。
  先在那台电脑上打开查看器。**查看器版本须 ≥ 0.34**（0.33.x 加载 JPEG 图像会卡死，0.34.0 修复；这里的发送端受 LeRobot 限制为 0.33.1，已验证 0.40.0 查看器可正常显示）：

  ```bash
  uvx --from rerun-sdk==0.40.0 rerun --bind 0.0.0.0     # 或：pip install rerun-sdk==0.40.0 && rerun --bind 0.0.0.0
  ```

  然后再在 SSH 里运行 `./teleop.sh`。查看器没打开时脚本会提示并退出。

> 原版 `lerobot-teleoperate` 每个控制周期（60 Hz）都发一帧 JPEG（约 6 MB/s），其中 2/3 是重复帧。
> 查看器处理不过来时会反压，把遥操作主循环卡在 `rr.log` 上，从臂不再跟随主臂，
> 日志出现 `Sender has been blocked for over 5 seconds waiting for space in channel`。
> 因此 `teleop.sh` 通过 `teleop_viz.py` 按摄像头帧率发送图像。不要用网页版（`--serve-web`），它处理不了这个数据量。

启动前先把两只手臂摆成相近姿势：启动瞬间从臂会直接转到主臂姿态。按 `Ctrl+C` 停止，退出时从臂扭矩会释放，**注意扶住从臂以防下落**。

## 6. 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| `EOFError: EOF when reading a line` | 在非交互环境（如 `!` 前缀）运行了校准，换到独立终端运行 |
| `Permission denied: /dev/ttyACM*` | 用户不在 `dialout` 组，执行 3.1 中的命令并重新登录 |
| 找不到串口 / 舵机无响应 | 检查手臂电源和 USB 线；`ls -l /dev/serial/by-id/` 查看设备 |
| `Failed to open connection to X server` | SSH 会话没有图形界面，rerun 窗口打不开；`teleop.sh` 会改为发送到 `RERUN_VIEWER_HOST` 上的原生查看器 |
| 查看器一显示图像就卡死 | rerun 0.33.x 查看器加载 JPEG 图像的 bug，查看器升级到 ≥ 0.34（推荐 0.40.0） |
| 遥操作中从臂突然不跟随、查看器卡住 | 查看器处理不过来时会反向卡住遥操作。立即 `Ctrl+C`（扶住从臂），确认用的是 `teleop.sh`（经 `teleop_viz.py` 限流）和原生查看器 |
| 摄像头打不开 / `Device or resource busy` | 摄像头被其他程序占用（如 rerun 外的预览软件），关闭后重试；`v4l2-ctl --list-devices` 查看设备 |
| 遥操作时某关节方向或角度明显不对 | 重新校准该手臂，注意中间姿态 |
