# SmolVLA 真机入口异步推理接入（2026-10-31）

原 `rollout_smolvla.sh` 使用官方同步推理，完整块生成会阻塞控制线程。
本次按用户要求改为仓库内 `so101_async` 后端，继续使用 LeRobot 0.6.1
的 episodic 录制、机械臂限幅、reset流程及现有相机预检。
默认候选仍是20k；本次没有启动训练，也没有连接相机、串口或驱动机械臂。

## 实现与边界

入口：`scripts/rollout_smolvla.sh` → `so101_rollout.smolvla.rollout`。
实现：`src/so101_rollout/smolvla/async_engine.py`。
不修改已安装的 LeRobot 包。进程内注册新后端，并替换 rollout context
使用的工厂绑定；参数解析及20k检查点选择均已在硬件构建前截断验证。

- 目标20Hz，50步动作块；剩10步时在单独worker中提前生成下一块。
- worker串行执行模型、pre/post processor及CUDA工作，控制线程只拿CPU动作。
- 新块完成前继续消费旧块；完成后丢弃从观测时刻起已经过去的预测前缀，再替换未来命令。
- 控制循环延迟时跳过已经过去的tick，不追赶重放过期动作。
- pause/reset立即递增generation并清队列；旧在途结果不能回灌。模型/processor由worker在下一代请求开始时重置。
- 队列为空时不发送伪造保持动作；持续饥饿超过0.5秒退出，第一块等待上限30秒。reset后的等待也包括旧在途请求阻塞时间。
- 该实现没有启用RTC动作前缀引导，也没有插值、滤波或轨迹平滑；模型内动作噪声与颜色选择仍是独立问题。

官方RTC后端的 `reset()` 会直接清队列及调用模型/processor reset，未提供
本任务需要的在途generation屏障，因此没有仅切换 `--inference.type=rtc`。

## 离线验证结果

使用实际20k权重和已录制双色smoke数据，经新后端完整pre→policy→post流程：

| 指标 | 绿色 | 红色 |
|---|---:|---:|
| 有动作的tick | 400/400 | 400/400 |
| 饥饿tick | 0 | 0 |
| 动作可用频率 | 20.000Hz | 20.000Hz |
| 控制调用p99 | 0.927ms | 0.845ms |
| 动作可用间隔p99 | 51.02ms | 50.83ms |
| 动作可用间隔最大值 | 51.71ms | 51.83ms |

共完成21个动作块，0个跳过tick，丢弃72个过期预测前缀动作。
另强制等待worker实际开始红指令推理，再切换generation和绿指令：旧结果1个被丢弃，只有新绿色请求完成后才返回下一代动作。
首次块等待约0.60秒（绿，冷启动）和0.20秒（红）。

该测试仅测**录制观测下的异步动作供给**，不包括相机采集、串口发送、
Rerun、数据写入或真实运动。间隔存在操作系统抖动，不能宣称每个tick严格≤50ms，
也不能据此认定真机平滑或抓取/选色成功。遥测的action时间是取出CPU动作的时刻，
早于串口发送；官方录制仍保存限幅前目标，数据集timestamp仍是frame_index/fps。

正常路径真模型检查之后又补充了“旧推理卡住时reset也受startup timeout约束”的故障边界，
使用阻塞worker和受控时钟回归验证；该补丁没有改变本次成功路径的调度。

证据：`/data/work/so101-evidence/real-robot/smolvla-async-rollout-integration-20261031-final/`，
包含 `report.json`、`telemetry.json`、双色动作数组、配置解析检查及命令。
测试包含并发隔离、过期前缀、慢tick跳过、异常/非有限输出、饥饿、观测快照、启动超时及入口参数。
最终仓库全套测试 **406 passed（11.17秒）**，证据在上述目录的 `tests-final/`。

主Agent另用官方 `send_next_action`、`ActionInterpolator` 与fake robot复核了跨块及reset的实际适配，
完成68次fake发送，未连接硬件。证据：
`/data/work/so101-evidence/real-robot/smolvla-async-rollout-integration-20261031/root-dispatch-verification.json`。

## 下一次监督真机测试

保持双色物理布局 green A1 / red C3，空碗，同一折叠初始姿态；每条结束恢复。
用户在场时使用新数据集名分别测试：

```bash
TASK="Put the green cube into the paper bowl" \
  ./rollout_smolvla.sh eval-smolvla-20k-async-green-r1-20261031 1

TASK="Put the red cube into the paper bowl" \
  ./rollout_smolvla.sh eval-smolvla-20k-async-red-r1-20261031 1
```

每次启动仍需通过相机预检。异步遥测写入该次预检证据目录的
`async-telemetry.json`。先分别记录抖动、首次选择颜色和最终入碗，
不能把“动作供给20Hz”代替这些实机结果。
