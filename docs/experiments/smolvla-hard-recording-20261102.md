# SmolVLA 原hard控制的完整推理记录（2026-11-02）

受约束过渡没有通过验收，本轮只增加默认关闭的诊断仪表，保留原hard替换、模型内随机采样和调度逻辑。未连接相机或机器人、未发动作或训练。真实权重+预录观测的无硬件backend smoke与完整归档审计均已通过；下方提供用户一次性集中完成12条基线诊断采集的执行包，待主审后交付。

记录设计：`INFERENCE_RECORDING_PATH`或`--inference.recording_path`显式开启；原request的deepcopy快照在LeRobot原地转换前由推理worker保存。另保存实际模型preprocessed输入、模型原sample_noise产生的tensor、完整反归一化50×6输出。noise捕获仅在worker私有model实例上临时包裹原方法，原参数调用原方法并返回同一tensor，finally恢复，不新增随机采样或更换noise参数。相同RNG的开关输出与CPU/CUDA RNG状态均须逐元素相等。

控制线程只提交小型事件：request ID/generation/task/dispatch时间、安装时old/new对齐future及expired prefix、每次实际CPU输出、reset/stale/failure/stop。磁盘使用独立writer线程压缩npz，不用pickle；队列默认256条、128MiB未压缩array+JSON负载上限，满则丢日志并计数，不等待磁盘。错误、丢失、未clean close或close超时均使status.complete=false，并在最终telemetry.stats.recording显式记录；日志故障不传播为控制故障。初始status不完整，防止异常退出假称完整。

原图、numpy dtype和tensor原始字节无损保存；模型输入不缩放、不变换。observed_at是host request dispatch单调时钟，不是相机曝光时刻；上游未提供相机曝光时间，不能凭日志补造。相机快照是当次真正推理所用的输入。记录目录与模型解析路径、全部模型文件SHA/config、代码SHA、action order、fps/horizon/prefetch/device绑定；模型hash在首次推理worker启动阶段计算，不在20Hz控制线程读盘。

## 验证结果

证据根目录`/data/work/so101-evidence/real-robot/smolvla-hard-recording-20261102/`，最终真实backend结果位于`final/report.json`，归档重放审计位于`final/archive-audit.json`。

| 检查 | 结果 |
|---|---|
| 同观测/同seed，记录关闭与开启 | 输出逐元素相同，CPU/CUDA RNG状态逐元素相同 |
| 两色20Hz，每色160tick | 321次实际CPU输出（含reset后验证首步），无starved/skipped |
| 真实worker generation屏障 | 已运行旧请求1次被丢弃，未装入新代queue |
| green控制调用p95 / max | 0.211 / 1.207ms |
| red控制调用p95 / max | 0.194 / 1.162ms |
| 日志完整性 | smoke共372/372条写成，丢失0、错误0、complete=true |
| 预测归档 | 等RNG验证1次+smoke10次，共11套原始观测/实际noise/完整预测 |
| 直接用保存noise逐chunk重推 | 11次，maxdiff=0 |
| 从原始观测重做preprocessor | smoke10次，实际模型输入逐元素相同 |
| raw chunk到安装future的时标 | 9次安装，expired前缀共24步，逐元素一致 |
| CPU输出queue重放 | 321次输出逐元素一致；stale chunk保留用于审计但未安装 |

两色首块等待0.876/0.172s，前者包括模型目录hash读取；不在控制活跃后同步hash。smoke目录约28MiB，只代表本次录制输入与16秒运行的证据大小，不保证真实相机采集的存储量。归档保留原numpy/tensor数值，不用有损JPEG；模型输入维度与内容均不改变。读取图像数组前检查schema/meta的480×640×3维度，没有展示图片。

测试覆盖慢写盘、队列item/bytes上限、磁盘失败、close超时、已有目录不覆盖、标量/bfloat16无损往返、reset屏障、日志失败时仍正常发CPU输出、慢写且队列满时控制不阻塞、默认无记录/显式启用与launcher拒绝已有路径。全套 **428 passed（12.66s）**，见`tests-final.log`；代码编译检查通过。原nonfinite、slow inference、expired-prefix scheduler测试继续通过；不把日志故障混同模型故障，模型异常原先的停止行为保持。

首轮审计工具比较postprocessor的CPU输出与恢复到CUDA的archive tensor时出现device不一致，修复比较端设备后重跑；失败证据保留在同级`smolvla-hard-recording-20261102-failed-device-comparison/`。没有模型/控制故障。最终`final/`运行包含实际processor配置、代码/launcher/模型实现SHA及argv，和准备交付的runtime代码对应。

## 可复现与归档审计

```bash
# 新目录，无相机/机械臂；真实backend、真实权重、预录观测
HF_HOME=/data/models/huggingface HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=src:. \
/data/work/venvs/so101-smolvla-061/bin/python tools/smolvla_recording_check.py \
  --output /data/work/so101-evidence/real-robot/smolvla-hard-recording-NEW

# 检查归档索引、request/观测/预测配对、raw→安装、queue输出；不连硬件
PYTHONPATH=src:. /data/work/venvs/so101-smolvla-061/bin/python tools/smolvla_recording_audit.py \
  --recording /data/work/so101-evidence/real-robot/smolvla-hard-recording-20261102/final/smoke

# 加载精确本地权重，重做preprocessor与逐chunk模型重推；仍不连硬件
HF_HOME=/data/models/huggingface HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=src:. \
/data/work/venvs/so101-smolvla-061/bin/python tools/smolvla_recording_audit.py \
  --recording /data/work/so101-evidence/real-robot/smolvla-hard-recording-20261102/final/smoke --replay-model
```

局限：20Hz验证没有包含相机采集、串口发送、Rerun和视频编码并行负载；记录enabled增加了推理worker内的CPU/GPU快照复制和writer CPU/I/O，不能保证硬件环境下无影响。控制输出是后端实际交给rollout的CPU目标、在机器人max-relative限制及串口发送之前，不等于电机真实运动。output.time沿用scheduler的本次控制调用起始单调时刻，安装有installed_at、推理有begin/end、请求有observed_at；不伪造相机曝光或电机发送时间。

## 用户集中完成12条采集

这是原hard控制的诊断采集，不是优化已成功版，也不评估失败的project/gate策略。用户一次取得全部方案，自行逐条恢复、集中完成，最后统一通知；无需每条向agent确认。本轮真机仍0/12，未自动运行任何live命令。

执行包：`/data/work/so101-evidence/real-robot/smolvla-hard-recording-20261102/collection-package/`。其中`INSTRUCTIONS.md`含12条编号/布局/目标/独立可复制命令，`plan.json`冻结模型所有目录文件、相关runtime/launcher、相机/机械臂配置SHA和参数；`results.csv`是12行人工结果表。12个launcher命令均以DRY_RUN实际验证返回0，见包内`dry-run-validation.json`。

选择四组各3条，每条单独进程/独立dataset/episode0。有限驱动程序最多执行12条，在每条之前用本地Enter等待用户恢复完成；不使用20s自动reset窗口，也不自动开始无限新轮。正常单条结束时官方teardown默认约3秒平滑回该进程startup初姿，然后断开；须等待回位完成后再摆放。四组及所有单条都在启动前恢复同一个批准初姿，不能把上一条末姿当新初姿。两种布局保持G C2/R C3、R C2/G C3，目标各green/red，每组3次。

先检查方案（默认只打印，不接硬件）：

```bash
python3 /data/work/so101-evidence/real-robot/smolvla-hard-recording-20261102/collection-package/collect.py
```

主审后由用户在本地前台终端执行整个有限包（这条会连接硬件；本轮未执行）：

```bash
python3 /data/work/so101-evidence/real-robot/smolvla-hard-recording-20261102/collection-package/collect.py --execute
```

驱动先校验冻结SHA及12组fresh dataset/记录目录，再逐条等待Enter；q可结束剩余条目。任何launcher非0或日志不完整就停止，不自动下一条。ctrl-C结束整个包；→提前结束当前episode，Esc停当前记录进程；←会丢弃重录当前条，不用于保留失败。键盘事件依赖本地桌面pynput/焦点，用户在启动前验证停止入口，不能假设SSH终端键盘有同样语义。

每条前摆好布局、纸碗、同起姿/夹爪、线缆和空间；launcher会先相机预检，再连接串口。记录目标是否正确、首次接触位置、是否夹起/入碗/碰推、异常折叠/展开/撤离、中止原因。进程退出后填`results.csv`；异常中止保留失败，不能直接当专家训练样本。

数据路径`/data/work/so101-datasets/<plan.dataset>/`；完整诊断在包内`recordings/trial-XX/`，原终端输出在`terminal-logs/trial-XX.log`，预检/遥测路径与退出码记录到`trial-XX-execution.json`。用户完成后一次性交回执行包路径与填好的CSV即可，主agent据真实request/chunk交接定位问题。新会话若路径已存在，用工具指定新session生成新包，不能覆盖或混用RESUME：

```bash
python3 tools/prepare_smolvla_baseline_collection.py \
  --output /data/work/so101-evidence/real-robot/smolvla-hard-collection-NEW --session NEW
```

最终`final/code-binding-verification.json`确认实际backend归档中的全部5个代码SHA与当前源码匹配，集中采集包的全部冻结输入SHA也与当前文件一致。
