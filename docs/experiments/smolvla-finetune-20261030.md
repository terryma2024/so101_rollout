# 2026-10-30 SmolVLA 首轮微调：准备与顺序启动

用户授权：在antzb安装并锁定依赖，当前RED ACT运行期间不启动SmolVLA GPU任务；双任务数据与训练脚本在本机训练smoke通过后，持久排队等待RED ACT成功结束，立即启动首轮微调。主方案见[训练与Rollout计划](../plans/smolvla-training-rollout-plan-20261030.md)。运行状态以证据目录的PID、日志、时间戳、退出码和队列状态为准。

**交接状态（2026-10-30 15:56 CST）：准备与验收完成，antzb持久队列已启动，PID2740784，状态`waiting_prerequisite`。** 此刻只有RED ACT训练进程PID1545954，约69369/100000步；SmolVLA没有started标记或正式输出目录。队列在RED成功退出后自动派发，不需要Agent继续在线。不能将“已排队”理解为“正式微调已运行”。

## 首轮参数与本机smoke

最终配置：batch32、20000步、seed1000、FP32、图像增强关闭（库默认），保留base的`freeze_vision_encoder/train_expert_only/train_state_proj`默认值。AdamW学习率1e-4、betas(0.9,0.95)、weight_decay1e-10、grad_clip10；cosine decay末端2.5e-6。配置保留preset1000/30000，0.6.1按20k预算实际缩放为warmup666、decay20000。每5000步保存并对完整17864帧验证，约10.04轮训练帧采样。

本机100步采用相同batch和数据/模型/处理器链路：3200样本含1646绿、1554红；loss/梯度全部有限，最后单步loss0.310338、gradnorm1.725900；峰值显存8719462400字节（8.12GiB）。checkpoint000100在CPU严格重载450046176参数通过，预处理state/action及反归一化action的均值方差与train统计逐值一致。独立抽查expert q_proj参数确已更新，max绝对差0.00323486。

smoke验证只采64帧（每色32）检验链路，不将其loss0.2206解释为全52条的泛化结果。正式训练才执行完整留出评估。当前388项完整仓库测试通过，证据`full-tests-wmonqrx0/`；数据和训练包另经独立审查。

## 已批准数据

源为已验收green133条44794帧及red133条36802帧，不使用P0评估，不重新纳入已排除示范。按完整来源录制folder冻结划分，再拟合train统计。

| Split | Green | Red | 合计episode / frames |
|---|---:|---:|---:|
| Train | 101条 / 33291帧 | 113条 / 30441帧 | **214 / 63732** |
| Validation | 32条 / 11503帧 | 20条 / 6361帧 | **52 / 17864** |

Train来源：green pilot61、green P2第一批10、green P2 extra接受30、旧red clean92、red P2 extra21。Validation来源：green adjacent32、red P2第一批20。clean来源保留原episode映射，原数据不改。

来源组、原episode和完整数值轨迹hash均无跨split交集；不宣称布局、日期独立或不存在视觉近似场景。派生目录：

```text
/data/work/so101-datasets/real-cube-bowl-smolvla-train-20261030
/data/work/so101-datasets/real-cube-bowl-smolvla-validation-20261030
```

任务0为`Put the green cube into the paper bowl`，任务1为`Put the red cube into the paper bowl`。状态/动作6维，20Hz，双图640×480。

Train统计只从63732训练帧拟合；validation自身描述统计保留用于审计，另有`meta/normalization-reference.json`指向train stats及SHA。此引用不是LeRobot自动机制，实际train/validation共用train-fitted处理器，由专用入口与smoke证明。

163192视频帧完整解码、532个真实loader首尾读取、逐episode数值匹配、数值和图像摘要统计检查通过。7来源102文件及既有两批准集20文件SHA不变。工具：[prepare_smolvla_data.py](../../tools/prepare_smolvla_data.py)。批准receipt SHA256 `9c4347abc9a3b012aa8fa017babc8775612e301b7d01c23679df81eb2fa1b1cd`；派生manifest SHA256 `09c6450b6b17de5ce36f7579db8ed5dbbdabe1bbbd1551aeb6fcd4effbbb5f88`；train stats SHA256 `a894ea726894265d450f20acb9382be79a8372bbf6a7648a74735675720e5842`。

## 环境、模型与入口

两机独立环境为`/data/work/venvs/so101-smolvla-061`。完整传递依赖锁见[smolvla-cu130-py312.txt](../../tools/locks/smolvla-cu130-py312.txt)，实际freeze和安装命令留在证据。现有ACT环境安装前后freeze须相同。

antzb实际114个锁定包与本机ML环境逐项一致，只排除训练不需要的本repo应用wheel；Torch2.11.0+cu130、torchvision0.26.0+cu130、LeRobot0.6.1、transformers5.5.4。安装/验证仅CPU，CUDA未初始化，ACT freeze前后完全相同。

官方base/VLM处理器revision与[本机smoke](smolvla-local-smoke-20261030.md)固定值相同。传输实际文件并核对SHA，不只复制Hub共享blob软链接。bootstrap保留官方权重字节，仅将VLM/tokenizer固定为本地快照，设置`load_vlm_weights=False`，明确camera1=wrist、camera2=side、缺省camera3、state/action6维。

[train_smolvla.py](../../tools/train_smolvla.py)只在本进程替换数据factory与审计hook，优化、反向传播、batch、保存与评估仍用LeRobot0.6.1。官方`dataset.eval_split`按每task末尾拆分，无法表达本次32G+20R整组留出；adapter直接加载批准的214/52，字段中的总留出比例仅为记录/guard。**配置不能交给裸lerobot-train二次拆分，启动与恢复须用adapter。** 不修改安装包。

预处理state/action和反归一化action均核对train均值方差；记录双色实际tokens、采样量及finite loss/梯度。逐色validation loss按有效动作时间步加权，scalar保持官方`loss.sum()/valid_entries`语义，不能乘padding比例后按固定长度平均。

首轮预算20000步，每5000步保存并评估；正式validation用完整52条。batch以本机100步smoke最终通过配置为准；保留base默认冻结策略和学习率preset。scheduler会按总steps自动缩放，记录生效配置，不只引用base原始warmup值。

## 持久启动队列

新工具[queue_finetune.py](../../tools/queue_finetune.py)不改旧green→red队列。每15秒检查RED ACT严格`exit_code=0`、100000步config和权重非空、固定PID身份的原进程已退出。再复核数据、环境、模型、本机smoke四份批准回执，以及run.sh/config的冻结SHA。run.sh另验文件树、活跃trainer、独占锁和输出不覆盖。

队列有持久启动/派发回执、锁和原子status；重复派发保留日志/PID并拒绝，失败不自动重试。前置失败或消失且无成功证据则停止，不启动SmolVLA。Agent结束后队列持续运行；整机重启自动恢复不在功能内。

正式模型目标：`/data/work/so101-policies/real-smolvla-red-green-v1-20261030`。

队列批准文件`queue/approved.json` SHA256为`ee694e78a43bd758ed87d7353ccbd1568b735bcf02a9036aedd2698ee8f96766`，固定四份批准回执及正式`training/config.json`和`training/run.sh`。远端guard已实际通过数据/模型/源码/版本检查，然后正确因RED trainer仍在运行而拒绝；未执行提前训练。启动脚本SHA256为`194625ed854fd70ea0afc27035056958f1d11609caf107d5c4f4042d4bef579e`，正式config SHA256为`7b21038ef782e50d2df09ec44d1c55f247fac130551c1e3906b682c5a384cb5d`。

查看实时状态（只读，不重复派发）：

```bash
ssh -T antzb 'cat /data/work/so101-evidence/real-robot/smolvla-finetune-20261030/queue/queue_status.json'
```

## 证据与后续

根目录`/data/work/so101-evidence/real-robot/smolvla-finetune-20261030/`：

- `data/build-01/`：split、来源映射、源/派生SHA、统计、视频/loader验证和独立review；临时`source-views/`不上传。
- `data/transfer-01/`、`data/transfer-approved.json`：两机文件集合/SHA校验及传输批准。
- `training/`：独立环境、模型、完整配置、smoke、checkpoint重载及正式脚本。
- `queue/`：最终批准链、持久PID/status/log、部署和轮询确认。

Validation loss不是抓取或语言选色成功率。正式训练产物返回后，仍按主计划的固定物理布局、双指令配对协议做实机评测。
