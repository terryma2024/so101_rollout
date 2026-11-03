# SmolVLA v2：36条补采清单（2026-11-02）

最新分析：其他位置16条已完成，成功7/16；建议把原36条局部补采调整为覆盖三组位置对的72条。原36条清单暂不执行，新方案尚未采集或启动训练。详见[综合结论](smolvla-other-positions-conclusions-20261102.md)。

**2026-11-02 最新执行顺序：先优化并验证单进程模型复用的有限测试入口，再用现有20k基线完成其他位置16条回归；根据实测结果决定是否扩大或调整补采。36条补采保留为待执行方案，当前不推进补采或训练。以下原计划和既有证据保留，涉及“先补采”的旧顺序以本条为准。**

状态：仅准备文档与空结果表，尚未采集、连接硬件或训练。正式采集需操作者在场逐条遥操。36条是首轮补齐起点，不是足量或泛化改善保证。

## 方案与摆放

3个独立重摆批次×2布局×2目标颜色×3位置变体，共36条。每批12条，按颜色分两个folder，各6条；B01/B02整批24条预分配train，B03整批12条预分配validation。整个批次（含两色folder）必须同split；不能只换目录名制造独立性。每批重新拿起摆放两块，重新建立机械臂初姿并记时间。同日独立重摆不代表日期独立。

A布局：绿C2/红C3；B布局：红C2/绿C3。方块中心对格中心，边平行纸面格线（0°）。每条人工恢复同一机械臂初姿、夹爪状态与遥操流程；碗、光照、相机保持现状。

**三种位置是：名义格中心0mm；两块一起沿纸面印刷列号递增方向平移+3mm；两块一起反向平移−3mm。行轴偏移0mm。方向依据纸面坐标，不是相机左右或机器人轴；不要只动目标块，不要把3mm当一整格。**

| 批次 | split | 颜色顺序 | 每色episode 0→5（布局/共同偏移mm） |
|---|---|---|---|
| B01 | train | 绿→红 | A/0, B/0, A/+3, B/+3, A/−3, B/−3 |
| B02 | train | 红→绿 | B/0, A/0, B/−3, A/−3, B/+3, A/+3 |
| B03 | validation | 绿→红 | A/0, B/0, A/+3, B/+3, A/−3, B/−3 |

颜色按folder分开，folder内交错布局；禁止同folder混红绿任务文本。每条仅抓指令色放入碗，另一色留在相应格位。

覆盖审计初步证据：266条中精确绿C3/红C2下，抓绿2条均validation，抓红2条均train；反向精确布局0。每色距指定格≤1正交格（4cm，含exact）的near-neighbor：绿C2/红C3下绿train7/val7、红13/0；绿C3/红C2下绿7/5、红11/0。近邻经验存在，但红指令近邻validation为空。首帧布局审计不能替代全程动作质量审查。保留旧split追加24/12后总计238train（绿113/红125）、64validation（绿38/红26）；最终以接受条目为准。

## 六条命令（人在场逐条执行）

工作目录 `/home/matianyi/Projects/so101_rollout`。现有环境 `/data/work/venvs/so101-real-lerobot-061`，输出 `/data/work/so101-datasets/`。下面命令尚未执行；每folder初次须不存在。完成一个folder并核对后再执行下一条，不拼无人值守循环。

1. B01 / train / green

```bash
TASK="Put the green cube into the paper bowl" ./record.sh real-cube-bowl-smolvla-v2-b01-green-20261102 6
```

2. B01 / train / red

```bash
TASK="Put the red cube into the paper bowl" ./record.sh real-cube-bowl-smolvla-v2-b01-red-20261102 6
```

3. B02 / train / red

```bash
TASK="Put the red cube into the paper bowl" ./record.sh real-cube-bowl-smolvla-v2-b02-red-20261102 6
```

4. B02 / train / green

```bash
TASK="Put the green cube into the paper bowl" ./record.sh real-cube-bowl-smolvla-v2-b02-green-20261102 6
```

5. B03 / validation / green

```bash
TASK="Put the green cube into the paper bowl" ./record.sh real-cube-bowl-smolvla-v2-b03-green-20261102 6
```

6. B03 / validation / red

```bash
TASK="Put the red cube into the paper bowl" ./record.sh real-cube-bowl-smolvla-v2-b03-red-20261102 6
```

## 预检与冻结

现有record.sh先按camera.env锁定曝光/白平衡，再跑双相机preflight，写独立record-preflight目录与decision.json。失败、异常、超时或无法保存证据时停止查因，本方案不采用输入y绕过。结果表记每次预检目录。现有侧相机检查在启动时和默认每10条保存后运行；6条folder不保证中途检查。显示沿用本地/远端rerun配置。

plan.json记录当前arms.env、camera.env、preflight及参考图、录制和相机源码SHA。执行前核对；若SO101_CONFIG_DIR或串口/相机/SIDE_*环境变量有覆盖，先记录并核验实际值。SHA只检测文件变化，不证明实时相机控制或物理位置。WRIST_WB当前为auto，不能描述成两相机白平衡均锁死。

若其他色差会话修改相机参数、预检参考或配置，暂停核验差异和画面，不覆盖或偷偷还原其配置。本包不调参、不生成新运行包装器、不训练。

## 按键与恢复

n/→结束当前阶段：录制中结束本条，复位中提前进入下一条。r/←丢弃当前缓冲并重录同一episode索引。q/Esc退出，但非空当前缓冲仍可能保存，不等于作废当前条。结束键有1秒防抖，避免连按。

单条最多30秒；条间20秒是**人工复位窗口，遥操仍运行，不会自动回初姿**；到时自动进入下一条。操作者应在窗口内完成机械臂和方块复位，确认阶段后才按n。来不及应停止检查，不能把准备动作作为合格示范。保存通常在复位窗口之后，须等落盘后认定提交。

中断后读取该folder `meta/info.json` 的total_episodes=k，核对episode元数据/视频及结果表，索引须为0…k−1；不能用尝试次数当保存数。空缓冲保护会不保存但仍消耗本次循环次数。未保存重录维持原plan_id；已存失败或错摆条目也占索引，标拒绝交主流程处理，不能擅自删文件、重编号或错配下一计划行。

已核本机LeRobot源码：每次recorded_episodes归零，num_episodes表示本次新增尝试数量。因此已有k条合格且映射正确时，从CSV的第k个索引开始，使用原任务/原目录续录6−k条。例如已有2条，执行 `RESUME=1 TASK="原任务文本" ./record.sh 原名字 4`；不可再次传6。k=6无需续录，k>6或索引不一致先暂停核验。异常退出不能假设末条已保存；续录后再次查落盘数。

## 清单与验收

证据目录 `/data/work/so101-evidence/real-robot/smolvla-v2-collection-20261102/`：plan.json含6个folder和配置SHA；placements.csv含36条及每folder准确计划索引0…5；results.csv含36行not_recorded，实际索引与结果留空，须实际核对后填入。记录正确选色、夹起、入碗、误碰、质量接受、时间、预检目录、side日志、操作者与备注。

每folder结束核对6条落盘、任务单一、两相机视频完整、状态/动作有限、20Hz及图像规格正常；逐条复核后才接受。计划条目不等于已验收示范。失败原始证据保留并另行处理，不为凑数隐去拒绝项。后续合并仍须全量视频解码、来源与数值审计、轨迹去重及stats重算，本包不生成训练数据。

源码依据：scripts/record.sh、src/so101_rollout/operations/record_viz.py和本机lerobot/scripts/lerobot_record.py的recorded_episodes循环、人工reset、save_episode及finally；绝对路径与SHA见plan.json。
