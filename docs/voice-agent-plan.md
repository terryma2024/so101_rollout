# 方案一：语音选择红/绿 ACT 的抓取 agent（只用 LeRobot，不用 ROS）

日期：2026-10-28。状态：已确认（2026-10-28 16:05），P1-P6 离线开发中。

确认时的决定：
- 麦克风用 USB 麦克风，还没到货。先用键盘兜底验证全流程，语音识别模块照常写好并用样本音频测试。
- 指令语言：中文为主，同时认英文关键词（red / green / stop），成本很低（按"选推荐方案"的规则定）。
- 绿色策略用 REAL-ACT-002（ckpt 100000）。红色策略在 REAL-ACT-RED 拉回之前，离线演练用 REAL-ACT-001 顶替。

## 目标

一个常驻进程，同时加载两个 ACT 策略。人说"红色"或"绿色"，从臂就用对应的策略把那块方块放进纸碗，做完回到休息位，
等下一句话。说"停"随时停下。

- 红：REAL-ACT-RED（antzb 训练中，约 17:40 完成，`real-act-red-20261028/checkpoints/100000`）。
- 绿：REAL-ACT-002 或 REAL-ACT-001，看今天对照实验的结果选成功率高的。
- 两个模型都放 GPU（ai-station 是 RTX 5060 Ti 16 GB，ACT 每个约 200 MB 显存），切换不需要重新加载。

## 设计

### 控制循环（`voice_runner.py`）

- 和 `lerobot-rollout` 用同一套接口：`SO101Follower`（同样的两路相机配置、`max_relative_target=30`），
  `predict_action`（`lerobot/common/control_utils.py`）加上策略自带的前后处理器。实现前先读 `lerobot_rollout.py`，
  观测的构造、设备和数据类型与它保持一致，这样策略看到的输入和评估时完全一样。
- 20 Hz。每次开始一个任务先 `policy.reset()`，任务文本用训练时的原句（"Put the red cube into the paper bowl" /
  "Put the green cube into the paper bowl"）。
- 结束条件（先到先算）：
  1. 语音"停"；
  2. 超时 30 秒（和采集、rollout 一样）；
  3. 完成判定：夹爪闭合过再张开，之后机械臂离休息位每个关节都在 10° 以内并保持 1 秒（演示数据都以回到休息位结束）。
- 结束后 2 秒内插值回休息位（和 rollout 复位相同的姿态），然后等下一条指令。
- 执行中收到新的颜色指令：不打断，提示"正在执行"。只有"停"能打断。
- 可选 `--record <数据集名>`：每次执行存成一条评估数据（LeRobotDataset，任务文本同上），之后用现有的检查脚本分析。

### 语音（`voice_asr.py`、`voice_intent.py`）

- 本地识别：faster-whisper `small`（多语言，CUDA int8_float16）。模型下载到 `/data/work/models/faster-whisper-small`。
- 麦克风流（sounddevice，16 kHz 单声道），按能量切出一句话（静音 0.6 秒结束一句），送去识别。识别在单独线程，
  不阻塞 20 Hz 控制循环。
- 意图只看关键词，不用大模型：
  - 含"红" → red；含"绿" → green；同时含两个或都不含 → 不执行，提示"没听清，请说红色或绿色"；
  - 含"停""停止""别动" → stop（任何时候都有效）；
  - "回去""复位" → 回休息位。
- 键盘兜底：终端里输入 `红` / `绿` / `停` 回车，效果相同。没有麦克风也能用，测试也靠它。
- 反馈先只用终端打印和提示音，不做语音播报。

### 环境

- 新建 venv `/data/work/venvs/so101-voice-lerobot-061`：同一个 lerobot 0.6.1，外加 faster-whisper、sounddevice。
  采集和训练用的 `so101-real-lerobot-061` 不动。

### 安全

- 只有人在机械臂旁边时才跑真机。
- `max_relative_target=30`，和 rollout 一样。
- Ctrl-C：先停策略，回休息位，再断开。
- 识别结果和每次执行的开始、结束原因都写日志（`/data/work/so101-evidence/real-robot/voice-agent-<日期>/`）。

## 实施步骤（Sonnet 子代理执行，我审查）

1. **P1 环境**：建 venv，下载 whisper 模型，记录版本和 sha256。
2. **P2 意图与完成判定**：`voice_intent.py`、完成判定函数，加单元测试（关键词表、合成的关节轨迹）。
3. **P3 语音**：`voice_asr.py`。能量分段用合成音频测试，识别器用假对象测试。真实识别用你录的几句话样本单独验证。
4. **P4 控制循环**：`voice_runner.py`。用假机器人、假策略、假时钟测试状态机：开始、停、超时、完成、回休息位、
   执行中收到新指令。
5. **P5 入口**：`voice_agent.py` 和 `voice_agent.sh`，加载两个策略，接上语音和键盘输入。
6. **P6 离线演练**：不连机械臂，用数据集里的帧当相机输入，确认两个策略都能出动作、单步推理时间满足 20 Hz、切换没有延迟。
7. **P7 真机（你在场）**：先用键盘指令红、绿各 2 次，再用语音红、绿各 5 次，记成功率和识别错误。

测试只用夹具数据，不读 `/data/work` 下的文件。P1-P6 不需要机械臂，可以在 REAL-ACT-RED 训练期间做完。

## 已定事项

1. **麦克风**：USB 麦克风，到货后再做 P7 的语音部分。主板插孔麦克风的测试（2026-10-28）收不到人声，不再使用。
2. **语言**：中文关键词为主，英文 red / green / stop 也认。
