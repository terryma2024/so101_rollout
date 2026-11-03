# SmolVLA 数据优先 v2：审计、重组/补采、重训、12 条回归（2026-11-02）

## 2026-11-03 执行更新（优先于下文历史状态）

用户已授权在本机重新训练；antzb 已下线，本轮不向 antzb 传输或启动任务。继续沿用下文的数据、CPU验收、真实100步smoke和正式20k训练门槛，但正式运行位置改为本机，新建v2输出，不覆盖v1。

扩大后的72条补采已完成数值完整性和视觉抽样审核。红36条可保留；绿原36条中G19（B02-green episode 6）抓错红块，排除该条。2026-11-03补录目录 `real-cube-bowl-smolvla-v2-wide-g19-replacement-green-20261103` 的episode 0已通过完整性和视觉抽样审核（313帧、15.65秒），替代G19并归入B02训练来源组。原数据保留，禁止把错误G19与替代条同时纳入。

本轮新增train48、validation24；保留旧214/52划分后，目标合计train262、validation76。B01/B02用于train，B03整组用于validation；同批红绿保持相同group。具体来源与SHA以即将导出的冻结manifest为准。这些计数是审核后的选择目标，不代表合并或训练已经完成。

审核证据：
- `/data/work/so101-evidence/real-robot/smolvla-wide-green-audit-20261102/visual/visual-results.json`
- `/data/work/so101-evidence/real-robot/smolvla-wide-red-audit-20261102/visual/report.md`
- `/data/work/so101-evidence/real-robot/smolvla-wide-g19-replacement-audit-20261103/`（numeric、visual及selection.json）

本机初次资源检查：RTX 5060 Ti 16GB，GPU利用率0%，显存338MiB；数据盘可用946GiB。此为准备时快照，正式启动前重新确认。执行证据拟写入 `/data/work/so101-evidence/real-robot/smolvla-v2-local-training-20261103`。

以下保留历史方案与约束，其中36条、尚未采集、antzb正式运行等旧状态由本节替代。

最新分析：其他位置16条已完成，成功7/16；建议把原36条局部补采调整为覆盖三组位置对的72条。原36条清单暂不执行，新方案尚未采集或启动训练。详见[综合结论](../experiments/smolvla-other-positions-conclusions-20261102.md)。

**2026-11-02 最新执行顺序：先优化并验证单进程模型复用的有限测试入口，再用现有20k基线完成其他位置16条回归；根据实测结果决定是否扩大或调整补采。36条补采保留为待执行方案，当前不推进补采或训练。以下原计划和既有证据保留，涉及“先补采”的旧顺序以本条为准。**

本轮已授权顺序为：完整数据审计 → 按覆盖结果平衡重组或补采 → 重算 train-only 统计并冻结新 manifest → CPU 验收 → 本机真实训练 smoke → antzb 正式重训 → 原 12 条同条件复测。各门槛满足后继续执行；需要人手示范时一次性交付采集包并等待实物数据。本文不是 GPU 启动回执。本次准备审计没有启动训练、连接硬件或修改远端。

## 当前证据与选择

v1 批准数据为 train 214 条/63732 帧、validation 52 条/17864 帧；总红绿各133条不代表颜色×位置×布局条件平衡。来源、规范化与首轮参数见[首轮微调记录](../experiments/smolvla-finetune-20261030.md)。完整来源/布局/质量覆盖见[独立数据审计](../experiments/smolvla-data-coverage-20261102.md)及其266条逐episode明细。本轮全部初帧覆盖核验、0条新全程动作审查，复用既有81条过程抽帧资格，不能写成全部266条全程重审。G C3/R C2同格green两条均在validation，red两条均在train；G C2/R C3未辨识到同格示范，近邻数据存在，不能等同该位置从未见过。决定先补采36条，再验收追加；不搬两条green拆来源组。

2026-11-02 12:25 CST 对 antzb 只读检查：RTX5080，534/16303MiB、利用率0%；`nvidia-smi` 无 compute-app，进程查询无训练器/旧队列活跃匹配。`/data` 可用81GiB（82%已用）；v1 train约1.2GiB、validation334MiB、policy6.0GiB、证据886MiB。旧队列状态 `completed`、理由 `exit_code=0`；020000权重文件存在。独立环境 Python 可导入元数据：Torch2.11.0、torchvision0.26.0、LeRobot0.6.1、transformers5.5.4；三份旧 environment/model/local-smoke receipt 存在。这仅核实存在与版本，未重做完整freeze/hash批准。GPU空闲只是一刻快照，启动前仍须复查独占锁、活跃训练器、磁盘预算与最新批准。

主方案从与 v1 相同官方 base 重新训练20k，不从旧20k继续。继续训练会混入已有20k历史数据暴露、额外步数、优化器动量及LR恢复/重启、旧处理器归一化状态；即使仍称“20k”也不与base→20k可比。相同base重训减少这些混杂，但数据删选、split、stats和新训练帧数都会改变；固定640000次帧采样后的 effective epochs = `20000*32/N_train_frames`，不能宣称只变一个变量。

## 数据门槛与分支

覆盖审计已交付旧266条来源、布局、未知项和质量范围，并决定补采36。后续新数据验收仍需以下输入：

- 全部接受数据的 source folder、原episode映射、SHA、任务、帧数；排除记录与原因；完整来源组身份，不能只以clean派生目录作来源身份。
- 两色×目标位置C2/C3×双色交换布局×采集session的成功质量表，以及接近/夹起/入碗的判据和不确定标签；区分双色共现与单目标画面。
- 现有可用成功轨迹是否覆盖 green-C3；各格独立来源组数、轨迹长度和重复/近似场景说明；不能用重复长轨迹或每色133条填覆盖格。
- 补采36的执行包见[补采清单](../experiments/smolvla-v2-collection-20261102.md)；待实物数据验收后提供新逐episode manifest路径与实际train/validation计数。现在仅有frozen-split-reference.json旧引用，尚无ready v2 manifest；没有生成的目录不得写为已验收数据。

质量门槛：任务文本与实际成功目标一致、状态/动作6维20Hz且有限、两相机640×480同步范围完整、无损坏/缺失视频、源数据和批准排除项不变。失败策略rollout、12条回归记录和P0评估不直接当专家示范。完整来源录制组必须只属一个split，原episode与完整数值轨迹hash不能跨split；同一session拆成几个新文件不能制造独立留出。validation需含两色及关注的换位条件，并尽量来自新增独立采集批次；仅整folder留出不能宣称日期/布局独立。未知覆盖明确保留未知。

若现有成功示范已充分覆盖关注条件且存在可信完整组留出，则不强制补采：冻结成功子集和整组split，按颜色×目标位置/布局检查episode和frame两种平衡；记录删选损失与采样分布，重导出独立v2目录，再推进CPU验收和训练。若整来源组约束使平衡或关键留出无法同时成立，不能拆组凑数，应补采。

本轮36条为有界起始设计：2种双色交换布局×2条目标指令×3种位置条件×3个独立批次=36。位置条件为两块共同沿纸面列号方向−3/0/+3mm，保持相对关系，角度先0°；固定双色坐标后恢复同布局录不同指令，不能随目标颜色交换位置。这与早先“只偏移C2”的建议不同，以本次审计/补采包为准。每批12条件，B01/B02共24条train，B03完整12条validation；每批两个颜色folder共同属于一个group，不得按folder随机拆批次。全部验收通过并保留旧split时预计train238（G113/R125）、val64（G38/R26），实际帧数未知，失败/unknown会改变计数，入口以实际冻结manifest为准。先逐条验收成功和覆盖，再决定重录或追加；36不是确认最小值或充分数量。最终未见日期/微扰布局另留测试。

## 冻结与训练兼容门槛

v2 manifest至少记录split、color/task、完整group（共同采集批次）、source_dataset、source_episode_index、original_episode_index、origin（原录制folder:原episode）、derived_episode_index、frames、numeric_sha256、质量判定及来源SHA；group与origin独立，同批红绿folder可共享group但origin仍唯一；同一原source folder只能属于一个group。批准文件同时冻结manifest SHA、两split完整文件清单及SHA、train stats SHA、来源未变化证明和审计版本。保留v1原目录和旧receipt，新建v2目录和新证据根；所有待生成路径均为规划，当前不能启动。

重组后必须对新train的state/action等全部数值特征重新拟合，按split本地episode聚合图像统计并验证。validation自己的描述stats保留审计，`meta/normalization-reference.json`指向新train stats路径与SHA。训练和验证实际共用train-fitted pre/postprocessor，CPU严格重载检查pre-state/pre-action/post-action均值方差逐值一致；引用JSON本身不会使LeRobot自动采用train stats。

旧数据导出器和启动壳仍不能直接用于新数据：`prepare_smolvla_data.py`硬编码7来源与整源聚合；训练prepare/adapter的旧硬编码本轮已改成验证后的manifest计数/帧数，具体接口如下；`run_smolvla_training.sh`硬编码v1数据/输出路径。不得裸调用lerobot-train重新拆分，也不能把旧run.sh指向v2数据当完成准备。data exporter须按coverage结论实现新来源追加/验收，v2 run.sh另写并冻结，不能复用旧固定路径。

固定训练契约：相同base revision `5e8d12a6e2975b0e5e5fce7c8caf47c371d257b6`、base权重SHA `7cd549ac2351fb069c0ddb3c34ad2d09cfc92b56a15dccdfc2e41467aaca01eb`；相同VLM/tokenizer revision `7b375e1b73b11138ff12fe22c8f2822d8fe03467`。bootstrap只调整离线路径/输入契约，权重与官方base逐字节一致；load_vlm_weights=False。FP32、AMP关闭、augmentation关闭，freeze_vision_encoder/train_expert_only/train_state_proj均true。batch32、steps20000、seed1000、workers4、prefetch2、persistent_workers=true；AdamW lr1e-4、betas(0.9,0.95)、eps1e-8、weight_decay1e-10、clip10；cosine末端2.5e-6。保留preset warmup1000/decay30000，0.6.1按20k实际缩放warmup666/decay20000，记录生效LR而非只读配置。每5000步保存/全量validation，max_eval_samples=0。

CPU阶段验收新manifest与实际parquet逐episode/count/frame/task一致、来源组/原episode/hash不交叉、完整视频解码、真实loader首尾、stats直接重算、源和派生SHA、processor、模型/依赖/源码冻结及adapter相关测试。之后本机真实数据batch32至少100步smoke：双色token不同且均采到、loss/梯度有限、真实参数更新、显存、保存后CPU strict reload与新train stats一致；smoke证据不得冒用v1 receipt。再传antzb核全树SHA及freeze，绑定新config/源码/launcher/数据/模型/local-smoke批准；不覆盖任何v1输出，GPU空闲/独占锁通过后才正式20k。正式产物CPU重载并核完整步骤/双色全量验证，再返回本机。

## 复测与可复用检查

复测用原2布局×2指令×3次=12条，保持hard、20Hz、horizon50、prefetch10、MAX_REL30、双相机映射camera1=wrist/camera2=side、光照/相机预检阈值与物理相机、起姿、碗和控制代码一致。只更换模型及其训练得到的processor并冻结新SHA，保留原始request/noise/chunk/CPU输出记录；不同时部署blend/project/gate、固定noise或换相机参数。每条独立恢复，记录正确选色、夹起/入碗、首次接触、重试/碰推、中止、限幅与换块d1/d2、饥饿/跳tick。新建12条执行包和空结果表，旧包不可覆盖/直接执行，因为它冻结旧模型。原12条已用于诊断和开发，是回归集；改善不能当未见泛化证据。

以下仅为当前存在对象的只读命令：

```bash
ssh -T -o BatchMode=yes -o ConnectTimeout=12 antzb 'nvidia-smi; df -h /data/work; cat /data/work/so101-evidence/real-robot/smolvla-finetune-20261030/queue/queue_status.json'
rg -n '214|52 / 266|63732|validation-root|output_dir' tools/{prepare_smolvla_data,prepare_smolvla_training,train_smolvla,guard_smolvla_training}.py tools/run_smolvla_training.sh
```

训练命令必须在上述门槛完成、生成并验证新config/manifest/launcher后写入新证据；本计划不提供指向未生成目录的可执行启动命令。


## 本轮训练入口改动与验证

`prepare_smolvla_training.py`新增可选`--split-manifest`，输入JSON顶层为`records`。每条必须显式有derived_episode_index（各split从0连续且唯一）；旧v1早期split.json没有该字段，不能直接当新接口输入，需使用经过核验的最终episode-map记录生成新冻结manifest。新prepare验证实际derived parquet每条task、frames、numeric SHA、info总数及原source parquet的对应episode；source根当前要求与train/val同属datasets父目录。因此新source目录及数值轨迹也必须传到antzb，单传派生两目录不够。clean旧数据保持已知删条索引映射，不能伪造original index。

prepare输出config旁的`config.split.json`，冻结manifest绝对路径/SHA、两split根与实际episodes/frames、train stats SHA。adapter自动读取sidecar并重新验证，按实际train帧数记录epoch预算、按真实counts拒绝加载器不匹配。guard同时要求sidecar的manifest SHA等于transfer批准及本机smoke批准SHA，实际文件树、stats、模型/源码、环境与训练独占检查仍保留。adapter在result里保存contract，`verify_smolvla_training.py`将其manifest SHA带入新smoke/final CPU receipt。新环境/模型/源码receipt须包含这些已改工具及sidecar，不能复用旧adapter SHA批准。sidecar引用是固定绝对路径，跨机器部署时保持路径一致或重新生成并验收，不能手改已批准receipt。

无sidecar兼容仅限v1原目录名、已批准stats SHA及214/52与63732/17864计数；v2缺sidecar明确拒绝。legacy回退保留旧参数与路径行为，不是给任意新split绕过manifest的接口。`prepare_smolvla_data.py`及旧run.sh本轮未改。

测试先观察新接口缺失、shared-group identity误拒和伪造original identity误接受的失败，再修复；覆盖空split、缺色/错task、frames/count/mapping漂移、源episode漂移、跨split组、同source多group、同批双色同组接受、sidecar内容变化、transfer/local-smoke split不一致。命令（纯CPU）：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src:. .venv/bin/python -c 'import sys; sys.path.append("/data/work/venvs/so101-smolvla-061/lib/python3.12/site-packages"); import pytest; sys.exit(pytest.main(["-q"]))'
```

使用项目pytest加独立ML环境的pandas/pyarrow，关闭无关ROS pytest自动插件：默认自动插件加载曾因缺lark失败，并非训练代码失败。最终全套 **443 passed（12.59s）**；代码compileall及本次文件diff检查通过。另对真实v1全部266条最终episode-map在临时目录包装manifest做CPU核验，derived与7source数值逐条通过；对现有官方base/离线bootstrap执行真实prepare，在临时目录生成config/sidecar，优化器/scheduler/seed/workers/prefetch与旧config相等，batch32/20k、52/266比例及epoch10.04205正确，`torch.cuda.is_initialized()==False`，输出训练目录未创建。临时目录自动删除，没有产生伪v2训练数据或正式训练产物。
