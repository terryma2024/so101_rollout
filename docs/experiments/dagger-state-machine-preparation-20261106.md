# DAgger 采集状态机离线准备（2026-11-06）

状态：**未集成、未进行正式采集、未验证硬件控制**。`src/so101_rollout/dagger/state.py` 为独立纯 Python 生命周期契约；没有修改 SmolVLA rollout 入口、scheduler、串口驱动或 probe。测试中的 `offline:` 证据引用仅为离线夹具。

## 状态与边界

正常路径：

`idle → policy_executing → pausing → paused_holding → leader_aligning → ready → expert_correcting → wait_release → completed`

`start_policy` 开始策略；`pause_requested` 立即使本地 generation 加一并离开策略可接受状态。`hold_confirmed` 必须有证据引用才进入保持确认状态；`start_alignment` 开始对齐；`alignment_confirmed` 记录对齐证据进入 READY；`start_expert` 必须引用触发及 leader 释放读回证据才开始纠正。READY 本身不授权专家命令。首轮人工介入后没有返回 policy 的边。

`finish` 只能从策略或专家执行状态进入 `wait_release`：停止采集/纠正命令，保持并无限期等待操作员明确请求卸力。它不表示已经卸力。`release_confirmed` 是已完成动作的回执：adapter 必须先接到操作员明确卸力请求（例如回车），确认手臂得到支持，再执行卸力并验证 torque 读回；携带上述完整证据后才进入 `completed`。未介入的 policy episode 也通过该收尾边界结束。异常或急停通过 `fail(evidence_ref, now=...)` 进入 `aborted`；该入口自行使用当前 token，不会被调用方持有的旧 revision/generation 挡住。

每次有效事件产生不可变 `Transition`，包括前后状态、revision、generation、事件发生时间、事件类型、证据引用及 effect requests。每次转换都应切分数据 segment，边界帧不进入专家标签；只有 `expert_correcting` 状态下经独立数据验证的专家观测/动作对才是纠正候选。此模块不创建训练数据，也不审核纠正质量。

## effect 请求与 adapter 责任

暂停返回：

- `scheduler_pause_and_invalidate`
- `clear_policy_queue`
- `hold_follower`

正常 `finish` 额外返回 `stop_expert_commands`，不返回清理或卸力请求。只有异常终止额外返回 `request_safe_cleanup`。所有 effect 都是**请求**，从来不是已执行回执。安全清理必须由实际 adapter 按设备状态执行；不能把该字符串解释为无条件关闭 torque 或无人支持时卸力。清理出错需要独立保留原始异常、读回结果和人工处置证据。

现有 `AsyncChunkScheduler.pause()` 将 `_active=False`，经 `reset()` 提升 scheduler generation 并清空 `_queue`；迟到结果由 `_collect()` 按 generation 丢弃，进行中的 GPU 推理未必被取消。该函数不会产生 follower 保持命令。本模块没有调用它。

未来 adapter 必须串行执行状态转换和命令发出：暂停时阻止新 policy 命令，丢弃已取出但未发出的命令，调用 scheduler pause/invalidate，清空 adapter 自己的待发队列，记录本地 generation 与 scheduler generation 的映射，再根据实时 follower 位置执行保持并检查读回。两种 generation 不应假设数值相等。完成这些工作后才可发送 `hold_confirmed`，证据应能定位各步骤及读回结果。动作 chunk、pending command 及 observation 均不可跨 generation/segment 复用。

`accepts_policy_result(generation)` 仅计算离线资格，不验证 scheduler 状态、队列、设备姿态或物理安全。任何 `evidence_ref` 仅是调用方声明的定位引用，状态机不读取或认证其内容，不能用 `True` 代替真实证据。单元测试全部通过也不能视为完成硬件集成。

## 时间和拒绝规则

每个事件携带 `expected_revision`、本地 `generation`、有限且单调的 `occurred_at`。调用时提供单调控制时钟 `now`，默认事件最大年龄为 0.5 秒。过期、未来、非有限时间、旧/未来 token 及非法边均抛出 `InvalidTransition`，不改变生命周期状态或 token；不得靠重置状态机来重试旧命令。

PAUSING/PAUSED_HOLDING 等待上限为 60 秒，对齐 45 秒，READY 30 秒，参考独立 probe 的命令/对齐/READY 上限。达到期限（包括恰好等于）后确认事件拒绝；adapter 必须持续调用 `check_timeout(now=...)`，使超时进入 ABORTED 并执行停止/清理请求。WAIT_RELEASE 没有自动超时，正常收尾无限期保持等待操作员请求卸力；故障仍须立即调用 fail。没有后台线程或隐式计时器。policy/expert 活动期的遥测丢失、跟踪误差、设备异常及采集失败须由 adapter 的实时 watchdog 检测并调用 `fail`。

## 对齐参考与上线前缺口

`AlignmentReference` 仅保留 `tools/probe_leader_follower_handover.py::ApproximateAlignment` 中的实验参考：肘部残差上限 4°，其余 arm joints 1.5°，连续稳定窗口 1 秒，窗口跨度 0.35°；gripper 不属于该 arm gate。该配置不计算 gate，也不复制 probe 的电机读写。上线 adapter 仍须检查所有关节、nominal ramp 完成、连续窗口、最大采样间隔、READY 后持续对齐与独立 gripper 触发/释放读回。参考参数不构成适用于正式采集的硬件保证。

正式运行仍需实现和验证 scheduler/命令队列 adapter、实际保持与对齐、触发和释放读回、操作员支持后卸力、录制 segment 边界、异常清理、实时 watchdog 及设备级联调。此次准备不允许直接以该纯状态机驱动电机。

## 离线检查

`PYTHONPATH=src .venv/bin/python -m pytest tests/test_dagger_state.py -q`

覆盖正常顺序、非法转换、首次介入不恢复策略、旧/未来 revision/generation、迟到和非法时间、声明证据缺失或布尔值、纠正停止与卸力边界、超时 watchdog、异常安全请求与急停不依赖旧 token。
