# DAgger 数据契约草案（2026-11-06）

状态：**新格式离线草案，未接入采集、机器人、训练或既有数据转换**。`src/so101_rollout/dagger/data.py` 只提供 stdlib 校验与训练候选帧索引选择，不证明任何硬件安全条件。本文的新字段不可解释成已有 capture 实现。

## 已核对的现有行为

本机 `/data/work/venvs/so101-real-lerobot-061/lib/python3.12/site-packages/lerobot/` 的实现：

- `robots/so_follower/config_so_follower.py` 的 `use_degrees=True`；`so_follower.py:50–59` 为五个 body motor 选择 `DEGREES`（配置为 false 时是 `RANGE_M100_100`），gripper 是 `RANGE_0_100`。不能把现有 `.pos` 直接称作 raw ticks；也不能仅凭默认值断言历史每次采集的实际配置。
- `SOFollower.send_action`（205–232）接收绝对关节目标；若设置 `max_relative_target`，先读取当前 `Present_Position`，按目标与当前位置之差限幅，再写 `Goal_Position`，返回限幅后目标。它不是把输入解释成相对 delta；参数限制是每次相对当前值的最大差。body 为 degree 时差值同为 degree，gripper 差值仍是其归一化单位，不能统一叫“度”。
- `scripts/lerobot_record.py:289–338` 先采 follower observation，再取 leader action，经 teleop/robot processor，调用 `send_action`，最后 `add_frame`。虽然注释说保存实际 action，代码将返回值赋给 `_sent_action` 后没有用它，实际保存 `action_values`（teleop processor 输出）。机器人 processor 或 follower 限幅可使保存值与实际发出目标不同。
- rollout `strategies/core.py:270–305` 的 `send_next_action` 也忽略 follower 返回值，返回插值后的 `action_dict`；`strategies/episodic.py:232–243` 将该值与该循环的 observation 存盘。这不证明存盘值就是最终限幅目标。
- 本仓库 `scripts/record.sh` 配置数据集 20 FPS；`operations/record_viz.py` 包装录制/复位阶段，没有替换上述 action 语义。`scripts/rollout_smolvla.sh` 的具体部署配置应另存到新 capture manifest，不能由文件名推断。
- `smolvla/recording.py` 的诊断 `observed_at` 是 host 请求 dispatch 时间，并非实测曝光时间；异步策略的推理请求 observation 与某个动作实际执行时的 observation 也不必相同。LeRobot 帧/FPS 时间不能作为实际 send 或曝光时刻的证据。

**send 成功返回仅证明调用正常返回并提供最终发送目标，不证明机械臂已达到目标。** `sent_action` 和后续 `observation_state` 必须分开。写入途中失败也不能声称没有 motor 收到命令，应标记未知/失败并停止候选选择。

## 建议的落盘结构

每 episode 一个 `manifest.json`、只追加的 `frames.jsonl`、`transitions.jsonl`，另存图像/视频及其索引与校验和。下面都是待实现字段；离线 helper 仅验证其中用于筛选的最小子集，不能代替正式采集验收。

| 层级 | 字段与含义 |
|---|---|
| manifest，helper 必需 | `schema_version=dagger-draft-1`；`source_session_id`、`episode_id`；任务原文 `task`；`layout_id`、`case_id`、`case_source`；不可变 `model_revision`；`action_keys` 与一一对应 `action_units`、与 action 同序的 `observation_state_keys`；`use_degrees=true`；`action_semantics=absolute_joint_target`；`clock=host_monotonic_seconds`；`capture_complete=true`、`action_mapping_verified=true`、`mapping_evidence_ref`。这些 true 只能由验收证据支持，不能给旧数据补默认值。 |
| manifest，正式 adapter 额外必需 | 原始数据来源、session/episode 起止与 clean-close/drop/error 统计；checkpoint/config/processor/code/calibration hash；follower/leader ID、有效 `use_degrees`、每关节 `max_relative_target`、action ordering、控制频率；模型推理配置与随机种子；相机配置、时间戳来源/时钟变换及图像索引；失败 case 的基线 session/trial/证据定位；评审人员/时间/规则与证据 hash。 |
| frame，helper 必需 | 严增 `frame_index`；`segment_id`、`state`、`state_revision`、`generation`、`control_source`、`boundary`；`observation_at`、`dispatch_started_at`、`dispatch_returned_at`；`camera_time_kind`；`observation_state`、`requested_action`、`processed_action`、`sent_action`；`send_succeeded`、`quality_valid`；`segment_review`、`segment_outcome`、接受时的 `review_evidence_ref`。 |
| frame，正式 adapter 额外必需 | observation acquisition 起止、各 camera 引用与 frame ID/年龄；leader sample 时间与原值；processor 输入输出引用；send 调用/异常证据；策略 request ID、调度 generation 与本地 generation 对应关系；推理所依赖 observation ID；事件前后归属与清队列确认；后续观测引用（不能把它写成 sent action）。 |
| transition | 使用 `state.py` 的 `before/after/revision/generation/occurred_at/event/evidence_ref/effects`；记录 effects 的真实执行结果。状态机只产生请求，并未实施硬件动作；本地 generation 不能默认等于 scheduler generation。 |

实际 SO101 顺序应通过 features 及 processor 审计固定为 `shoulder_pan.pos, shoulder_lift.pos, elbow_flex.pos, wrist_flex.pos, wrist_roll.pos, gripper.pos`（以实际版本审计结果为准）。在已验收 `use_degrees=true` 配置下前五项 `degree`、夹爪 `percent_0_100`。helper 强制该六轴顺序、逐轴单位、同序 observation state 和有限数；真实设备 features/processor 与此约定的映射仍需单独验收，不会替代实际范围或限幅验证。

## 时间与标签

同一 host monotonic clock，单位秒。`observation_at` 定义为当前控制循环获取观测完成的 host 时刻，不是曝光时刻；应满足上一 dispatch 返回 ≤ 当前观测完成 ≤ 当前 dispatch 开始 ≤ 当前 dispatch 返回。图像曝光若未知，`camera_time_kind=unknown`；unknown 时不得附带非空曝光时间或声称有曝光证据。若声明 `measured_exposure`，必须有 `camera_exposure_at` 与 `camera_timestamp_evidence_ref`，正式验收需进一步核实相机 clock 对齐。

训练配对是当前控制循环的 `observation_t` 与该观察之后专家发出的**最终绝对目标 `sent_action_t`**，不把它移到 `t+1`，不把之后的 measured joint state 当动作。保存 `requested_action`（专家意图）与 `processed_action`（发往 follower 的目标），保留三者差异，不静默覆盖。行为克隆若未来改用请求值作为标签，必须是单独版本与明确理由，不能混入本契约目标。

## 分段与筛选

canonical 专家状态为 `expert_correcting`；其余包括 `policy_executing`、`pausing`、`paused_holding`、`leader_aligning`、`ready`、`wait_release`、`completed`、`aborted` 均不能产生专家训练标签。开始专家对应 `start_expert`，但必须另有对齐/释放门控与真实 adapter 证据。每次状态转移、generation 改变、控制来源变化或 discontinuity 都创建新 segment；边界帧 `boundary=true`。

`select_expert_chunks` 仅选择同时满足：专家状态和 `control_source=expert`、非边界、send 成功、质量有效、**segment 明确评审 accepted 且 outcome success**。失败、abort、尚未验收的片段不会因为文件存在、teleop 参与或 policy 失败而自动成为专家数据。同一 segment 的评审/结果必须一致。若未来需要学习失败轨迹里的有效恢复，应单独切出可证实成功且独立验收的纠正 segment，保留原失败来源。

返回长度正好为 horizon 的滑窗索引；不 padding、不跨 index 缺口、segment、state revision、generation 或无效帧。动作 chunk 最后一帧不得跨到 hold、结束、复位或下一 episode。helper 的形状校验不会检查真实限幅，因为 `send_action` 内读取的 present 可能不同于先前 observation；正式 adapter 必须保存限幅读数/证据，用已记录配置验证 `sent − present`，不能臆定真机最大值。

`validate_split_groups` 强制一个 `source_session_id` 的所有 episode/纠正段仅属于 train/val/test 中一组。正式划分还应检查复用原视频、重复导出、基线 trial 派生关系，以来源连通组划分；不能重新命名 session 来避开泄漏检查。

## 图像完整性的明确限制

本次 helper 是 **numeric/control record validator**，函数名 `validate_capture` 只指本草案最小子集；它不读取、校验或证明相机图像/视频完整，也不证明帧同步。正式格式必须在 manifest 保存 `camera_mapping`，明确 `side`/`wrist` 到模型 image feature keys、分辨率、frame source、曝光时间 clock 的映射；每控制帧保存 `observation_images.side/wrist` 的 asset 引用、相机 `frame_index`、host acquisition 时间及未知/实测 exposure 信息，不复制图像到 JSON。二者缺失、坏引用、损坏文件、stale/重复帧、不明 clock 映射都应挡住正式 capture 验收；本次没有实现这层 serializer 或图像校验，不能据 numeric tests 声称数据可训练。

## 正式采集/旧数据映射阻塞验收

1. 用真实安装版本的 features、processor、有效配置与 calibration，证明每维顺序、单位、绝对目标语义；旧数据无法证明则隔离，不自动宣称已映射。
2. 实装并验证记录 follower 返回的最终限幅目标；证明 requested/processed/sent 区分、send 异常与不完整写入 fail closed。现有 recorder/rollout 保存值不能代替此证据。
3. 用安全受控验收证明观测/leader采样/send 的时序、camera freshness、generation 映射、清队列、边界标记、leader 对齐与门控；仅离线状态机测试不够。
4. 证明干净关闭、丢帧/异常检测、review 与来源链；失败 case 只作为纠正触发来源，冻结基线不被新标签或训练划分改写。
5. 旧专家数据应另做逐数据集审计。当前未证明所有旧 action 是否经过限幅/处理、实际 `use_degrees` 和完整 source-session lineage；这些是接受旧数据的阻塞项，不以默认值补齐。

离线验证：`PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_dagger_data.py`，37 项覆盖状态/来源/边界过滤、失败/待审拒绝、chunk 边界与缺口、时间顺序、非有限数、错误/遗漏/多余/重排关节与单位、未知枚举/曝光伪证、未证明映射与 session 泄漏。
