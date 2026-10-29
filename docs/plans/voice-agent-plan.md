# 方案一：语音选择红/绿 ACT 的抓取 agent（只用 LeRobot，不用 ROS）

日期：2026-10-28。状态：已确认（2026-10-28 16:05），P1-P6 离线开发中。

确认时的决定：
- 麦克风用 USB 麦克风，还没到货。先用键盘兜底验证全流程，语音识别模块照常写好并用样本音频测试。
- 指令语言：中文为主，同时认英文关键词（red / green / stop），成本很低（按"选推荐方案"的规则定）。
- 绿色策略用 REAL-ACT-002（ckpt 100000）。红色策略用 REAL-ACT-RED（ckpt 100000，2026-10-28 拉回；之前离线演练用 REAL-ACT-001 顶替）。

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

## 大模型理解（可选，`--llm`）

关键词规则听不懂自然说法（"拿那个绿的""先抓绿色的那个""把它放回去"）。`./voice_agent.sh --llm` 把这类句子交给
DeepSeek（`deepseek-flash`，`--llm-model` 可改），不加 `--llm` 时行为和以前完全一样。

- 需要环境变量 `DEEPSEEK_API_KEY`；没设置就在加载策略之前退出。key 不写日志、不进错误信息。
- 模型只能返回 `{"intent": "red|green|stop|home|quit|unclear", "reply": "<一句中文>"}`。intent 不在白名单、
  JSON 坏了、缺字段，都当失败。同时提到两种颜色、含糊、无关闲聊 → `unclear`，reply 里问清楚。
- 超时（`--llm-timeout`，默认 3 秒）、HTTP 错误、输出不合格 → 退回本地关键词规则，终端和日志里 source 写 `fallback`
  并带简短原因（`Timeout`、`http_401`、`bad_json` 等）。成功时 source 是 `llm`。
- **安全**：退出词照旧；然后永远先跑本地规则，命中“停”就立刻停，不调用 API。其它句子进后台线程按顺序请求，
  所以大模型在等的时候输入“停”仍然马上生效。
- 日志（JSONL）新增 `llm_intent` 事件：`channel`（键盘/语音）、`text`、`intent`、`source`、`latency_ms`、`error`、`reply`。
- stdin 结束（管道脚本）时，等所有已提交的指令都处理完、大模型请求都回来、机器人回到空闲，再发退出。
  这同时修了一个竞态：以前只看“队列空且空闲”，刚取出的“run”还没开始就被判成空闲，导致红色 0.0 秒就退出。

## 视觉验证和自动重试（可选，`--verify`）

默认关闭，独立于 `--llm`。需要 `DEEPSEEK_API_KEY`，没有就在加载策略之前退出。参数：`--max-attempts`（默认 10，>=1）、
`--verify-model`（默认 `deepseek-flash`）、`--verify-timeout`（默认 15 秒）。

- 一次执行结束（完成判定或超时）、手臂回到休息位后，在后台线程里把侧面相机（观测键 `side`）最新一帧编成 JPEG，
  发给视觉模型，要求返回 `{"visible": bool, "in_bowl": bool, "note": "<一句中文>"}`。控制循环不阻塞。
  模型先推理再回答，`max_tokens` 必须够大（2000），小了 content 会是空的。
- `in_bowl` 为真：成功，停。`visible` 为假：停，提示“目标方块不见了”（可能被碰出画面）。看得见但没进碗：自动再跑一次同一颜色，
  最多 `--max-attempts` 次，到了就放弃。
- 验证本身出错（超时、HTTP 错误、JSON 坏了、字段缺失或类型不对、visible=false 却 in_bowl=true）一律停止重试，只报错误类名或状态码，
  不写 key，不盲目重试。
- **安全**：“停 / 回去 / q”（键盘、语音、`--llm` 路径都一样）在提交的那一刻就取消整条重试链，在途的验证答案作废
  （epoch，和 `LlmWorker` 一样），之后的自动重试带着旧 epoch，进队列也会被丢掉。链进行中新的颜色指令被拒绝；
  执行中的拒绝提示不变。`max_relative_target` 和回休息位逻辑没动。
- 每次验证把 JPEG 和答案（含延迟、第几次、颜色）存到日志目录的 `verify/<时间>-<颜色>-a<N>.jpg|json`，并记 `verify` 事件；
  `run_start` 事件带 `attempt`。`--record` 时每次尝试各是一条 episode（等上一条存完再重试）。
- stdin 结束（管道脚本）时，`wait_until_settled` 等整条链（含在途验证和自动重试）结束再退出。
- 实现：`voice_verify.py`（`VisionVerifier`、`VerifyResult`、`VerifyChain`），`VoiceRunner` 只多了一个可选的 `chain` 钩子。

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
