# DAgger 正式采集准备

状态：离线准备；尚未接入真实 rollout、相机或机械臂，尚未产生 DAgger 训练数据。首轮选择 SmolVLA v2，ACT 后续独立验证。

## 已准备的内容

|内容|入口|范围|
|---|---|---|
|历史基线|[冻结档案](../baselines/pre-dagger-20261106/README.md)|12批次、194有效试次；失败/协助完成索引保留原始结论|
|采集状态机|[协议](dagger-state-machine-preparation-20261106.md)、[代码](../../src/so101_rollout/dagger/state.py)|纯离线转换、generation、过期事件、确认和终止请求；不是设备控制器|
|数据格式|[契约](dagger-data-contract-20261106.md)、[校验与筛选](../../src/so101_rollout/dagger/data.py)|动作语义、控制来源、专家段与分组；不是完整录像/LeRobot exporter|
|试采候选|[操作草案](dagger-pilot-cases-20261106.md)、[清单](dagger-pilot-cases-20261106.json)|先绿6、再红6；9个不同历史v2失败，红3个布局各重复两次|
|接管实验|[近似对齐](2026-11-06-bounded-approximate-handover.md)|独立探针，须通过真机验收后再做正式集成|
|实施分工|[离线准备计划](../superpowers/plans/2026-11-06-dagger-offline-preparation.md)|本次并行工作范围及后续集成门槛|

## 统一采集流程

自主策略先运行；操作者观察到实际失败后请求暂停。真正的执行适配器必须停止新策略命令、废弃已取出但未发送的动作、暂停异步调度器并使旧结果失效，然后保持 follower，确认后才对齐 leader。近似对齐和夹爪触发均需实测证据。人工接管后专家完成任务，不在同一条恢复策略。

正常结束停止跟随，follower保持最后目标，等待操作者托住并按回车卸力；不得增加自动卸力倒计时。状态机的确认事件只是适配器声明，不能替代真实动作及读回。故障退出独立处理，不等待正常结束确认。

保留策略、暂停、对齐、专家、收尾全过程及事件，但只有审核接受的有效专家纠正段可作为新训练候选。action chunk不能跨段，源session不能跨train/val。顺利自主完成的尝试保留为策略结果，不为凑数强行接管，也不计作恢复示教。

## 正式采集前仍需完成

1. 真机验证近似对齐在多个姿态下稳定通过，且接管首帧无目标跳变；异常退出也须验证。
2. 实现实际scheduler/发送队列/硬件适配器和事件录制；检验暂停后没有旧策略动作漏发，不把纯状态机测试当集成证明。
3. 明确请求动作、限幅后的实际发送目标、实测关节状态及观测时间对应关系。现有record路径可能保存发送前动作，旧数据与新纠正数据混合之前须单独审计。
4. 接入双相机并验证图像与数值帧完整、相机映射和时钟含义；数字字段校验不能证明这些条件。
5. 先验收一条完整纠正记录，再执行12次拟定尝试。实际获得的有效恢复段数量取决于失败是否出现及专家审核，不保证12条。

现有失败布局已用于开发与选场，后续参与DAgger后只能用于已知场景回归。新的独立验收集必须另冻结，不把旧验证集迁入训练。

## 离线复核

在repo根目录运行，不连接设备：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q \
  tests/test_dagger_state.py tests/test_dagger_data.py \
  tests/test_leader_follower_handover.py tests/test_leader_push_probe.py \
  tests/test_smolvla_async_engine.py tests/test_smolvla_async.py
```

这些测试验证离线契约和现有相关逻辑，不证明实际设备已暂停、已对齐、已卸力或正式采集可用。
