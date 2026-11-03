# SmolVLA other-positions 16条数值与完整性审计（2026-11-02）

**16条保存数据完整，共6681帧，全部真实CPU输出与dataset action逐元素一致，实际queue重建一致。运行过程有明确例外：case09发生29个饥饿tick、7个跳tick；case01和15是保留错误的采集恢复，不能统计为16条正常执行。** 本审计不以关节数值推断任务成功，视觉结论由独立视觉审计负责。

## 完整性与异常保留

源包：`/data/work/so101-evidence/real-robot/smolvla-other-positions-regression-20261102/collection-package`；分析证据：`/data/work/so101-evidence/real-robot/smolvla-other-positions-analysis-20261102/numeric`。未操作硬件、运行模型推理或训练；未改源dataset、recording、receipt或结果表。

- 16个独立dataset，各1个episode、episode_index=0、task_index=0；任务字符串与各自plan、request、reset完全一致。frame_index连续，时间戳为frame_index/20，state/action有限。
- 共7489个recorder条目；16个status均complete/closed=true，accepted=written=条目数，dropped=0、errors=[]、无close_timeout，条目编号连续。175份request/observation/inference完整对应，174次安装、158次后续边界；1份完成预测未安装，不视为执行过。
- 32路视频全部经ffprobe及ffmpeg完整解码，640×480、20fps，解码帧数均与各dataset对应，无解码错误。视频有完整编码不等于20Hz实时控制无遗漏。
- raw 50×6→trimmed future逐元素对齐，每个old future、install、CPU输出的queue重建一致，6681份output与dataset action逐元素一致。case09使用control tick→dataset row显式映射，未把缺tick补造为动作。
- case01：311帧；运行结束监听器cleanup报错`TerminalKeyListener ... ident`，原失败receipt保留；recovery仅接受采集完整。配置最长30s、有效视频15.55s，提前结束意图未知，不能据短视频判断完成或退出原因。
- case15：581帧、视频29.05s；用户确认超时仍夹物，未成功放置。退出disconnect写id6 `Torque_Enable=0`时返回`Overload error`；日志中的“after 6 tries”来自预构造错误文本，不能证明实际进行了6次写入，receipt保留错误与recovery。日志能确定退出时发生过载响应，过载首次开始时刻未知，未检查故障寄存器，不能倒推整段运行何时出现故障。
- case16：正常complete receipt，498项recorder条目、445帧，artifact/queue/video检查均通过。14条无receipt运行错误，01/15两条恢复；09仍属于这14条中的时序异常。
- 当前results.csv状态计数为`{'recorded_recovered': 1, 'not_run': 14, 'recorded_overload_exit': 1}`；这是人工标记现状，不作为完成采集或success的唯一依据。本审计未填写任务成功标签。

## 每条时序与交接

前5关节按use_degrees解释为度，夹爪为归一化值。d1为相邻保存CPU目标的最大body差，d2为相邻保存目标二阶差；均为MAX_REL限制之前的CPU目标，不是机械运动角度/速度/加速度。边界为后续install首输出；合并分位数合并原样本。case09跨缺口差单独标记，不能当50ms单步。

| ID | 布局 / 任务 | 帧数 | 输出Hz | 边界数 | 边界d1 mean / max | 块内d1 mean | 限幅告警 |
|---|---|---:|---:|---:|---:|---:|---:|
| 01 | G B1/R B2 / green | 311 | 19.976 | 7 | 3.957 / 15.894 | 1.563 | 0 |
| 02 | G B1/R B2 / red | 285 | 19.975 | 7 | 7.290 / 20.512 | 1.798 | 2 |
| 03 | G B2/R B1 / red | 582 | 19.976 | 14 | 14.118 / 62.714 | 1.880 | 10 |
| 04 | G B2/R B1 / green | 312 | 19.976 | 7 | 3.594 / 10.122 | 1.598 | 0 |
| 05 | G D3/R D4 / green | 582 | 19.976 | 14 | 12.410 / 39.604 | 1.613 | 6 |
| 06 | G D3/R D4 / red | 290 | 19.976 | 7 | 2.800 / 5.256 | 1.901 | 0 |
| 07 | G D4/R D3 / red | 271 | 19.976 | 6 | 12.354 / 60.195 | 2.080 | 10 |
| 08 | G D4/R D3 / green | 558 | 19.976 | 13 | 3.629 / 15.506 | 1.376 | 0 |
| 09 | G B1/R B2 / red | 545 | 18.754 | 14 | 13.740 / 67.169 | 1.776 | 9 |
| 10 | G B1/R B2 / green | 342 | 19.972 | 8 | 4.484 / 13.491 | 1.621 | 0 |
| 11 | G B2/R B1 / green | 444 | 19.972 | 10 | 3.400 / 17.229 | 1.279 | 0 |
| 12 | G B2/R B1 / red | 580 | 19.968 | 14 | 13.171 / 52.303 | 1.745 | 8 |
| 13 | G D3/R D4 / red | 240 | 19.975 | 5 | 2.681 / 3.726 | 2.093 | 0 |
| 14 | G D3/R D4 / green | 313 | 19.975 | 7 | 9.455 / 21.864 | 1.798 | 0 |
| 15 | G D4/R D3 / green | 581 | 19.974 | 14 | 8.883 / 25.707 | 1.850 | 1 |
| 16 | G D4/R D3 / red | 445 | 19.976 | 11 | 8.378 / 22.871 | 2.045 | 2 |

15条有效输出约19.968–19.976Hz，starved/skipped/stale均0；case09为18.754Hz，最长相邻输出306.14ms，warm inference p95=689.21ms、max=733.30ms。case10热推理max377.67ms、case12为331.17ms但queue尚未饿空；不能将推理耗时本身等同输出断流。case07单次输出间隔76.66ms，仍未计为跳tick。没有GPU/CPU并发遥测支持根因判断，不能指认为资源争用或persistent缓存污染。

case09输出control tick为0..580，却只有545帧，15段缺口共36tick，恰与29饥饿+7跳tick一致。dataset/video按保存帧20fps压缩为27.25s，而首末CPU输出host时间跨度约29.007s。视频frame307=15.35s对应control tick334=16.70s；之后所有时刻均须显式映射，不能直接对比dataset秒与control秒。request时间为主机dispatch时间，不是实测相机曝光时间。

| 连续15条（排除case09，非挑选成功） | count | mean | p95 | max |
|---|---:|---:|---:|---:|
| 边界d1 | 144 | 8.101 | 25.624 | 62.714 |
| 块内d1 | 5977 | 1.727 | 5.095 | 13.846 |
| 边界d2 | 286 | 8.503 | 26.996 | 65.814 |
| 块内d2 | 5820 | 1.759 | 4.186 | 13.661 |
| 实际state相邻步进 | 6121 | 1.310 | 4.659 | 9.582 |

全16条相邻保存输出的边界d1 mean/p95/max为8.601/28.403/67.169，包含case09跨缺口，不能直接与旧12连续控制边界5.833/21.273/45.910作同口径比较。排除case09后仍有case03连续交接62.714°、case07连续交接60.195°，说明hard目标交接冲突仍存在；布局、初姿、观测和noise均不同，这不是persistent造成退化的受控实验。

## 最大目标交接、实际state与限幅

| case / 视频时刻 | CPU d1 | 相邻记录state变化 | old future余量 | 视觉阶段 |
|---|---:|---:|---:|---|
| 09 / 15.35s（control16.70s） | 67.169 | 0.000 | 0 | 空爪撤回后准备重试；跨6control tick输出间隔 |
| 03 / 16.20s | 62.714 | 1.582 | 6 | 空爪撤回，随后再次接近 |
| 07 / 2.20s | 60.195 | 7.648 | 6 | 首次抬臂接近，尚未触块 |
| 12 / 22.25s | 52.303 | 1.319 | 5 | 多次失败后空爪撤回 |
| 05 / 2.20s | 39.604 | 2.374 | 6 | 首次抬臂，后续才到块旁 |

视觉阶段由独立视觉agent核对双视视频后提供，不以pan或gripper阈值推触物。case09最大差是最后保存目标lift −104.207→−37.038°，中间没有输出的tick329–333使queue已空，不能叫连续50ms换块跳变。日志该帧lift原目标−37.038→安全目标−74.484°、elbow41.003→61.033°；记录state lift−104.484°。该处state差0不证明没有内部电机运动，也不能将67.169°描述为机械臂瞬时转动。

case03 tick324连续目标lift −105.110→−42.396°，当前state−100.615°；旧future距state最大4.081°，新目标距state58.220°；日志实际lift限幅至−70.615°，elbow41.652→57.341°。这处旧queue仍有6步，目标冲突不能用queue饿空解释。case07 tick44目标lift−81.109→−20.914°，日志限幅为−35.099°，当前dataset state−64.835°；机器人send_action额外sync_read使安全目标与简单dataset state±30略有差别，不用dataset state伪造实际发送值。

48条实际MAX_REL告警按原目标唯一匹配输出，分布见上表与clamp-events.json；前5大目标差中case05没有限幅告警，因为新目标距当前state body最大28.772°，说明目标之间大差与相对state越界并非同一条件。全16实际相邻保存state步进最大9.846°，CPU目标与state最大距离70.873°；它们不能互相替代。

## persistent隔离、模型与相机条件

16条manifest的全部model文件hash一致，20k weights SHA256为`e96afce7f7bcb27237714421aa4f2e4360bc816ad3e89047363a0871ab0126bc`；core recording/async_engine/rollout/modeling_smolvla代码hash与原12条相同，launcher hash改变。hard、20Hz、horizon50、prefetch10、MAX_REL30参数一致，预处理双相机映射与输出6维契约保持一致。真实175份noise hash全部不同；这不证明统计独立或分解出noise因果。

receipt model_timings为进程累计历史，不能相加重复计加载次数：case01 loaded=true；case02开始新进程loaded=true，case03–15每条仅新增loaded=false；case16错误恢复后新进程loaded=true。因此本轮3次实际model load，13次复用。每条独立录档均有reset generation1→2（本次任务）→3（teardown），首request id/tick均0、所有request/output generation2，任务与各自dataset一致；没有跨case旧queue或任务字符串混入的记录证据。每条新engine的generation重复不表示全进程世代唯一。首request state与保存帧匹配除case15初始0.0879°差外均exact，case15后续request仍exact；初始request发生在启动等待前，不强行等于后来frame0。

这些证据说明记录输出契约与实际队列对应正确，没有发现可见记录污染；未用相同输入、相同noise对persistent和独立进程重跑，因此不宣称两个闭环轨迹逐元素相同，也不据核心hash排除所有缓存状态影响。

16条preflight、side alignment全通过；相较原12，arms.env/camera.env/preflight.json及lighting/alignment参考hash均一致。新16每条日志都保存V4L2实际读回：side手动曝光40、白平衡3000、饱和110、50Hz；wrist手动曝光40、饱和25、50Hz，但白平衡auto=1。原12 terminal缺少此读回块，不能仅凭配置hash说旧新实时设置/光照逐帧相同，腕相机自动白平衡尤其不能保证恒定。

新16实测side dx −1.492..−1.080px、dy−1.098..−0.583px、旋转−1.086..−0.947°、inliers47–57；背景亮度delta8.938–9.739、纸面ROI7.257–13.023。旧12纸面ROIdelta7.82–9.92，新16部分更高，尽管仍通过阈值15；参考相同、阈值通过不等于实时照明分布完全相同或与训练颜色分布一致。

## 结论与后续边界

保留16条作为已保存诊断数据，其中01/15恢复异常和09时序异常必须随数据一起使用。将09单列为系统时序失常案例；以其host时间和tick映射复核时间，不与正常20Hz轨迹混算机械速度。连续交接冲突可先用03/07/12作诊断样本，并把首次接近与撤回重试分开；选色、抓取、放置结论交由视觉，不能用平滑度替代。未授权新硬件试验或模型反事实，本审计到保存报告与证据为止。

复现工具：`tools/analyze_smolvla_recorded_trials.py --package <collection-package> --output <new-directory>`（队列/数值）；`tools/audit_smolvla_collection_integrity.py --package <collection-package> --output <directory>`（dataset/task/reset与全视频解码）。解释性证据包括trials、boundaries、clamp-events、pooled、pooled-excluding-case09、verification、run-manifests、source-sha256、integrity-extra及conditions-comparison.json；原12报告为[12条数值审计](smolvla-hard-12trial-numeric-20261102.md)。
