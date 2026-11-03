# 2026-10-30 SmolVLA 本机环境与离线频率测试

对应[训练与Rollout计划](../plans/smolvla-training-rollout-plan-20261030.md)的P1/P2。本次已完成独立环境搭建、官方base严格加载、真实录像的预处理/推理/反归一化以及FP32/BF16延迟测量。

结论：本机RTX 5060 Ti 16GB能运行SmolVLA，生成动作块的计算吞吐有余量；当前同步路径在块边界停顿约143–150ms，**不能保证连续20Hz控制**。后续优先验证后台提前生成动作块和动作衔接，而非仅切换BF16。

## 环境与模型

独立环境 `/data/work/venvs/so101-smolvla-061`，Python3.12、LeRobot0.6.1、Torch2.11.0+cu130、torchvision0.26.0、transformers5.5.4、accelerate1.15.0。`uv pip check`通过，原ACT环境freeze与安装前完全一致。直接依赖见[requirements](../../tools/smolvla-requirements.txt)，完整freeze与安装命令留在外部证据。

官方base `lerobot/smolvla_base`固定revision `5e8d12a6e2975b0e5e5fce7c8caf47c371d257b6`，权重906,712,520字节，SHA256 `7cd549ac2351fb069c0ddb3c34ad2d09cfc92b56a15dccdfc2e41467aaca01eb`。

VLM配置和tokenizer来自 `HuggingFaceTB/SmolVLM2-500M-Video-Instruct`，revision `7b375e1b73b11138ff12fe22c8f2822d8fe03467`。完整base使用`strict=True`加载全部权重，设置`load_vlm_weights=False`避免另下载一份随后被覆盖的VLM权重。模型缓存位于 `/data/models/huggingface`；Hub新缓存部分大文件是指向共享blob的链接，repo目录的`du`不代表实际权重大小。

## 测量方法

脚本：[tools/smolvla_smoke.py](../../tools/smolvla_smoke.py)。复现命令见[tools说明](../../tools/README.md#smolvla-离线延迟检查)，输出要求使用不存在的新目录。

- 输入来自已验收的green/red各133条派生集，实际解码各集首episode的8帧，frame index为0、10、…、70；提前从元数据确认640×480，再经实际dataset loader读取。录像加载不计入测量。
- `camera1=wrist`、`camera2=side`；输入两张真图，不传camera3，`empty_cameras=0`。按官方配置补边缩放到512×512；状态/动作6维，由模型处理padding。
- 使用base保存的processor和统计，task为两条既有英文指令；确认两条task产生不同、非空token序列。base统计仅用于此次运行/延迟检查，不是后续SO101微调的部署统计。
- chunk50、n_action_steps50、num_steps10、batch1，权重保留FP32；BF16是CUDA autocast计算模式，不等同于将全部权重转换成BF16。
- 每档顺序独占测试：1次cold、5次warmup、50次完整chunk、400个不sleep的select_action tick（每色4块）、200个50ms节拍tick（每色100）。每档原始样本656行。
- CUDA在计时边界同步，分别测preprocess、policy和postprocess；完整chunk检查finite，每次反归一化后的动作维度为`[1,6]`。不同任务开始前重置动作队列。
- 节拍回放采用“本次计算后睡满剩余50ms”，不按全局deadline补跑。报告动作就绪间隔、计算循环平均Hz和计算本身的超预算；不把调度抖动造成的微小50ms超出解释成模型推理stall。

## 结果

下表chunk包含处理器和一次动作反归一化，单位ms。

| 指标 | FP32 | BF16 autocast |
|---|---:|---:|
| 首次chunk（单次，非分位数估计） | 423.39 | 521.79 |
| 稳态chunk p50 / p95 | 149.51 / 151.03 | 142.88 / 144.60 |
| 稳态chunk p99 / max | 151.79 / 151.91 | 144.88 / 144.97 |
| 同步边界tick p95 / max | 150.28 / 150.36 | 143.42 / 143.46 |
| 边界tick超过50ms | 8/8 | 8/8 |
| 队列内tick p95 / max | 2.78 / 5.72 | 2.78 / 3.40 |
| 全部400tick超过50ms | 8/400（2%） | 8/400（2%） |
| 节拍回放平均Hz（green / red） | 19.21 / 19.20 | 19.27 / 19.26 |
| 最长动作就绪间隔 | 197.90 | 191.05 |
| CUDA peak allocated | 1.76GiB | 1.75GiB |

每块50动作在20Hz下可执行2500ms，稳态chunk不到152ms，说明具备尝试异步提前推理的计算余量。然而同步生成时会停住执行线程；边界之后还可出现约3ms的短动作间隔。因此平均19.xHz、甚至平均tick计算不到6ms，都不足以证明稳定20Hz。BF16相对FP32的中位延迟仅改善约4.4%。

## 范围与下一步

这次是离线计算预算测试，未连接相机、串口或机械臂，不含采集、限幅、录制、显示开销。只使用两套数据开头的少量真实观测，不是多布局鲁棒性或语言选色效果评测；未做训练forward/backward。base模型尚未针对本任务微调，不能用于直接实机抓取。

异步/RTC未在本次实现或验证。下一步先验证独立推理线程/进程提前补充动作队列，测饥饿、观测陈旧和动作衔接；指令切换必须清空队列并丢弃旧任务在途结果。随后按计划准备train-only统计的双任务数据，待antzb现有ACT结束后安排训练smoke及正式微调。微调产物返回本机后，以相同映射重新跑延迟测试，再验证含真实相机和串口的控制节拍。

## 证据与检查

证据根目录：`/data/work/so101-evidence/real-robot/smolvla-local-smoke-20261030/`。

- `setup/`：安装日志、`freeze.txt`、精确模型缓存文件SHA、GPU信息、`environment-verification.json`。
- `formal-fp32/`、`formal-bf16/`：`report.json`、全部`samples.json`/`samples.csv`、实际policy配置。
- `probe-fp32/`：早期小样本诊断，不用于正式统计。
- `tests-eyx_n8ay/`：主Agent独立执行2项deadline统计测试通过，含JUnit和console。另有作者测试回执。
- `root-verification.json`：主Agent复核两档原始样本计数、finite标记、延迟摘要与超预算次数、官方权重SHA，以及ACT环境freeze未变。

主Agent读取两份正式报告，检查两条task token不同、完整chunk样本数50、队列/边界分开、两档同步预算均未通过。独立代码审查无阻断发现，确认camera3省略及相对节拍测试的表述与代码一致；无需重复大规模测量。仓库代码未改现有机器人入口或ACT依赖。
