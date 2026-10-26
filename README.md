# SO101 机械臂环境配置手册

基于 [LeRobot](https://github.com/huggingface/lerobot) 的 SO101 主从臂（leader / follower）遥操作环境。

## 1. 环境概览

| 项目 | 版本 / 说明 |
|---|---|
| 系统 | Ubuntu (Linux x86_64) |
| Python | 3.12（由 uv 管理的 `.venv`） |
| LeRobot | 0.6.1，`lerobot[feetech]` |
| PyTorch | 2.11.0 + CUDA 13.0（RTX 5060 Ti 可用） |
| 舵机 | Feetech STS3215 × 6 / 臂，波特率 1 Mbps，ID 1–6 |

## 2. 硬件连接

两只手臂通过 USB 串口连接（CH343 芯片，`1a86:55d3`）。使用 `/dev/serial/by-id/` 路径，重新插拔后不会变化：

| 手臂 | 序列号 | 串口路径 | 当前设备 |
|---|---|---|---|
| 主臂 leader | `5CE5113682` | `/dev/serial/by-id/usb-1a86_USB_Single_Serial_5CE5113682-if00` | `/dev/ttyACM0` |
| 从臂 follower | `5CE5122459` | `/dev/serial/by-id/usb-1a86_USB_Single_Serial_5CE5122459-if00` | `/dev/ttyACM1` |

> `ttyACM0/1` 编号可能随插拔顺序改变，脚本统一使用 by-id 路径。

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
uv add "lerobot[feetech]"
```

### 3.3 验证

```bash
uv run python -c "import torch, lerobot; print(torch.__version__, torch.cuda.is_available())"
ls -l /dev/serial/by-id/
```

## 4. 文件说明

| 文件 | 作用 |
|---|---|
| `arms.env` | 主从臂串口路径和 ID（`my_leader` / `my_follower`） |
| `calibrate_follower.sh` | 校准从臂 |
| `calibrate_leader.sh` | 校准主臂 |
| `teleop.sh` | 启动遥操作（主臂控制从臂） |
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

启动前先把两只手臂摆成相近姿势：启动瞬间从臂会直接转到主臂姿态。按 `Ctrl+C` 停止，退出时从臂扭矩会释放，**注意扶住从臂以防下落**。

## 6. 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| `EOFError: EOF when reading a line` | 在非交互环境（如 `!` 前缀）运行了校准，换到独立终端运行 |
| `Permission denied: /dev/ttyACM*` | 用户不在 `dialout` 组，执行 3.1 中的命令并重新登录 |
| 找不到串口 / 舵机无响应 | 检查手臂电源和 USB 线；`ls -l /dev/serial/by-id/` 查看设备 |
| 遥操作时某关节方向或角度明显不对 | 重新校准该手臂，注意中间姿态 |
