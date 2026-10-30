# 2026-10-30 红色 ACT：P2 全量校验与顺序训练

用户已人工确认第一批20条无错色；第二批实采21条。授权整体校验，无问题后联合旧红色示范传至 antzb，待当前绿色任务完成后开启新版 RED ACT。

第一批审查见 `/data/work/so101-evidence/real-robot/red-p2-batch1-audit-20261030/summary.md`：20条6361帧全部保留，未发现抓绿记录，无删除；过程为双相机抽样复核，不将其等同于逐帧人工观看或已证明首次抓取成功。

本轮整体审查证据目录 `/data/work/so101-evidence/real-robot/red-p2-full-audit-20261030/`，训练交接 `/data/work/so101-evidence/real-robot/train-real-act-red-p2-20261030/`。确认通过后才能合并并生成远端数据批准回执。

来源为旧模型实际训练集 `real-cube-bowl-red-clean-20261028`（92条24577帧）＋P2第一批20条6361帧＋第二批21条5864帧，候选合计133条36802帧、20fps。接受清单和最终合并验证为准；不混入绿色示范或P0评估记录。所有原始数据保留并核对SHA256。

拟合并集：`/data/work/so101-datasets/real-cube-bowl-red-p2-merged-20261030`；模型输出：`/data/work/so101-policies/real-act-red-p2-20261030`。从旧 RED `train_config.json` 复用完整配置，只修改数据repo_id/root、job_name、output_dir。ACT从头训练，ResNet18骨干保留相同ImageNet预训练；batch8、100000步、每20000步保存、seed1000、chunk100、n_action_steps100、图像增强开启，不上传Hub。

顺序执行采用独立持久队列：当前绿色训练证据必须记录成功退出，并且100000步最终模型/config确实存在，才能启动RED；绿色失败或失去进程而没有完成证据时标注blocked并退出。等待过程中不占用GPU、不终止绿色、不更改训练环境。用队列锁与RED启动锁防止重复派发，状态和日志保存在训练交接目录。实际部署/启动以该目录回执为准。

实际审查结果：两批41条12225帧全部接受，拒绝0、不确定0；第一批源SHA与既有审查一致。第二批双相机过程抽样均红入碗、绿留桌，前臂入镜5条经加密抽帧未见触碰；第21条完整300帧，不是短条，41条数值轨迹无完全重复。首次抓取成功标签均保留unknown。

最终合并验证通过：133条36802帧；全数值逐行与来源一致，两路共73604视频帧完整解码，各episode时间边界及266个真实loader首末读取通过。全部数值特征逐episode/全局float64统计已重算复核，图像统计按官方摘要聚合通过。官方合并后11行元数据自指针在派生输出中修正为实际file-000，修复前证据保留；48个源文件SHA256不变。全部验证通过才生成verify_merge.json(passed=true)。

队列代码 `tools/queue_training.py` 与 `tests/test_queue_training.py` 已独立审查（Spec/Quality PASS）；完整仓库测试347项通过，证据 `/data/work/so101-evidence/real-robot/github-push-20261030/full-tests-rv4elc4h/`。队列持久后台运行、每60秒检查绿色完成状态；重复派发保留原日志和PID并拒绝，RED运行期间记录running_red。整机重启或人工终止后的自动恢复不在该队列功能内。
