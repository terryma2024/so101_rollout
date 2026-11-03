# SmolVLA 其他位置16条基线回归（2026-11-02）

状态：布局和顺序已在实测前冻结；**0/16真实执行，0/16完整记录，0/16人工任务判定**。单进程模型复用入口及无硬件验证已完成；由操作者一次启动、逐条Enter确认。当前没有连接机器人/相机、没有训练；36条补采保持待执行，根据这组回归结果再决定是否扩大或调整补采。

模型为现有20k基线：`/data/work/so101-policies/real-smolvla-red-green-v1-20261030/checkpoints/020000/pretrained_model`；`model.safetensors` SHA256为`e96afce7f7bcb27237714421aa4f2e4360bc816ad3e89047363a0871ab0126bc`。此组是有限回归筛查，每条件2次，不能证明统计泛化能力。后续新版必须使用同一布局、顺序和判据复测，不能看rollout表现后换格。

固定两个格对B1/B2与D3/D4，避开原C2/C3，分布在不同纸面区域；四个红绿互换布局在已有示范中均出现。选择兼顾不同区域及训练覆盖强弱的对照，不意味着全部条件充分训练。覆盖源为[266条episode审计CSV](/data/work/so101-evidence/real-robot/smolvla-data-coverage-20261102/episodes.csv)，按实际初帧名义格和task逐条计数：

| 布局 | 指令 | train同格 | validation同格 | 本轮重复数 |
|---|---|---:|---:|---:|
| G B1/R B2 | G | 0 | 1 | 2 |
| G B1/R B2 | R | 1 | 0 | 2 |
| G B2/R B1 | G | 20 | 0 | 2 |
| G B2/R B1 | R | 0 | 0 | 2 |
| G D3/R D4 | G | 0 | 0 | 2 |
| G D3/R D4 | R | 4 | 4 | 2 |
| G D4/R D3 | G | 2 | 2 | 2 |
| G D4/R D3 | R | 2 | 0 | 2 |

零计数只代表当前可辨识名义格的同任务组合没有命中；不表示邻域从未出现。格标签为4cm粗分类，来源含unknown和投影边界限制，不能声称毫米精度。详见[覆盖审计](smolvla-data-coverage-20261102.md)。

方块中心对准格中心，偏移0mm，角度0°；边平行纸面格线。每条恢复同一批准机械臂初姿和夹爪、当前行双色布局，碗、光照、相机不变。每个物理布局连续测试两条指令，指令改变时不要交换红绿位置。分两轮完整重复，交错指令次序以减小时间漂移：

| 执行号 | 布局 | 指令 | 重复轮 |
|---|---|---|---:|
| 01 | G B1/R B2 | G | 1 |
| 02 | G B1/R B2 | R | 1 |
| 03 | G B2/R B1 | R | 1 |
| 04 | G B2/R B1 | G | 1 |
| 05 | G D3/R D4 | G | 1 |
| 06 | G D3/R D4 | R | 1 |
| 07 | G D4/R D3 | R | 1 |
| 08 | G D4/R D3 | G | 1 |
| 09 | G B1/R B2 | R | 2 |
| 10 | G B1/R B2 | G | 2 |
| 11 | G B2/R B1 | G | 2 |
| 12 | G B2/R B1 | R | 2 |
| 13 | G D3/R D4 | R | 2 |
| 14 | G D3/R D4 | G | 2 |
| 15 | G D4/R D3 | G | 2 |
| 16 | G D4/R D3 | R | 2 |

固定20Hz、hard切换、horizon50、prefetch10、MAX_REL30，每条最多30秒，独立dataset episode0及完整inference记录；重用模型不能把不同case的动作队列、RNG/记录器、任务或episode历史混在一起。有限入口应一次启动到16条，每条等待本地Enter；中断后仅可从明确未执行编号继续，先核验已完成回执，保留所有失败和旧结果，不自动跳过未确认失败。

`config/arms.env`、`camera.env`、`preflight.json`在准备时逐项SHA与原[12条冻结plan](/data/work/so101-evidence/real-robot/smolvla-hard-recording-20261102/collection-package/plan.json)相等（分别`bad06666…222b5`、`6045e846…5c29`、`1e41c689…533`）。这只证明文件一致，不证明实时设备控制或物理场景未变；执行仍须原相机锁定与preflight。若冻结文件变动应停止调查，不能自动覆盖或恢复文件。

执行回执只证明程序执行状态；`status.json.complete`只证明inference记录完整性；CSV人工结果应独立记录目标选色、首次接触、夹起、入碗、碰推、中止和原因，未知保留unknown。日志完整不能替代任务成功，任务失败也不能删除或当专家示范补采。汇总须按8条件分别报告分子/分母，结合原C2/C3十二条对照，再决定问题是否集中在原位置及是否调整补采；不把16条直接合并训练。

最终包已冻结于[collection-package](/data/work/so101-evidence/real-robot/smolvla-other-positions-regression-20261102/collection-package/)，包含`collect.py`、`plan.json`、空人工结果`results.csv`、`INSTRUCTIONS.md`。本地前台终端一次启动整轮：

```bash
python3 /data/work/so101-evidence/real-robot/smolvla-other-positions-regression-20261102/collection-package/collect.py --execute
```

不传`--execute`仅dry-run打印16条参数审计命令，不连接硬件。`plan.json`中的独立case launcher保留作审计；请用上方整轮入口以复用模型。每条结束后等返回初姿、worker停止、设备断连，再动手恢复；下一条仍需本地Enter。

只有在两条之间输入q正常退出、之前case都有完整回执时，才可用同命令追加`--start-trial N`从明确尚未执行编号继续。恢复核验plan SHA、id/dataset/recording、实际完整记录、dataset meta及终端日志，剩余路径必须全新。Esc停止本轮并保留当前条；Esc/异常/半条不得盲目续到下一条、覆盖或删除后重试，先保留证据核验。

无硬件验证：最终包dry-run退出0且打印16条，布局/顺序/每条件2重复、16个独立dataset、CSV全`not_run`均已核验；18个冻结输入SHA逐项匹配，三个配置文件也与原12条冻结相等，无dataset/recording/执行回执或终端日志产生。[包核验JSON](/data/work/so101-evidence/real-robot/smolvla-other-positions-regression-20261102/package-verification.json)包含4产物完整SHA；`plan.json` SHA256为`3d5bfb0ce7d852f59607a97337c306408383201842da5b9f565a589a31f8fa4b`。主线程最终仓库测试453 passed；另有真实模型两case推理smoke：首加载13.25s、复用约0.00014s，模型实际加载1次，首动作1.35/1.15s；这不含硬件/preflight，不能代替真机实测。**真实执行、记录完整、人工任务判定目前仍各0/16。**
