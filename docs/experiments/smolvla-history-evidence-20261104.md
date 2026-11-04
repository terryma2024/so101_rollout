# SmolVLA 历史证据梳理（截至2026-11-04）

本文件供总报告引用；本轮仅离线读取文档、JSON和文本回执，未连接硬件、运行模型/训练或上传，未查看图片。新random20和adhoc评估由其他分析另行覆盖。下述视觉结论引用既有审核，未冒充本轮重新视觉验收。绝对证据根记为 `E=/data/work/so101-evidence/real-robot`。

## 1. 可追溯时间线

| 日期（CST） | 已发生事项 | 证据及解释 |
|---|---|---|
| 10-27至10-30 | 既有绿色pilot61+adjacent32、旧红clean92，以及P2绿40/红41，形成双色各133示范 | [覆盖审计](smolvla-data-coverage-20261102.md)、[绿P2](green-act-p2-training-20261030.md)、[红P2](red-act-p2-training-20261030.md)。这是SmolVLA复用的示范，不是SmolVLA策略rollout。 |
| 10-30 | 独立LeRobot0.6.1环境、官方base固定revision、双相机真实录像离线smoke；同步块边界超50ms | [环境/同步smoke](smolvla-local-smoke-20261030.md)。FP32每块p50 149.51ms，BF16 autocast142.88ms；8/8边界超预算，约19.2Hz。 |
| 10-30 | 离线异步原型通过正常20Hz供给，压力测试按预期失败 | [异步证据](smolvla-async-20261030.md)。90秒1800/1800有效输出，P99间隔50.038ms；额外800ms发布延迟导致24饥饿tick，不能用调度循环数冒充动作数。 |
| 10-30 | v1在antzb等待RED ACT成功退出后启动；20k最终完成并拉回 | [首轮准备](smolvla-finetune-20261030.md)15:56仍只排队；`E/smolvla-finetune-20261030/antzb-completed/training/final-model-verified.json`最终passed；finished为12:25:37Z，即20:25:37 CST。 |
| 10-31 | 首轮5k同步真机两条均失败，严重抖动；离线比较已有5/10/15/20k，选择20k继续试验，未立即重训 | `E/smolvla-rollout-diagnosis-20261031/REPORT.md`、`E/smolvla-checkpoint-comparison-20261031/REPORT.md`。 |
| 10-31 | 实机入口接入仓库so101_async，保持官方episodic/限幅/reset；离线真实20k双色各400tick供给通过 | [入口集成](smolvla-async-rollout-20261031.md)。本记录本身未触硬件，不等于真机验收。 |
| 11-02 | 相邻双色四条配对真机测试（名称仍含20261031）：红2/2、绿0/2 | [四条报告](smolvla-paired-rollout-20261102.md)。实际日期与数据集名日期不同；早期记录没冻结实际checkpoint SHA。 |
| 11-02 | 固定观测/噪声连续性离线实验；4/6tick短融合降低跳变但偏离大；后续约束候选均未通过留出stream | [连续性](smolvla-offline-continuity-20261102.md)、[约束过渡](smolvla-constrained-transition-20261102.md)。均未部署到runtime。 |
| 11-02 | 原hard策略加入默认关闭的完整推理记录，随后12条真实记录，目标入碗9/12 | [仪表](smolvla-hard-recording-20261102.md)、[12条数值](smolvla-hard-12trial-numeric-20261102.md)、`E/smolvla-12trial-visual-20261102/`。 |
| 11-02 | 32次有限反事实：16原配对全部精确复现；12组只换语言；2最大交接各做obs/noise交叉 | [反事实](smolvla-12trial-counterfactual-20261102.md)。诊断结束即停止，无新策略部署。 |
| 11-02 | 单进程模型缓存/有限人工会话；其他位置16条真机目标入碗7/16，促使原36条C2/C3补采扩至72 | [持久会话](smolvla-persistent-session-20261102.md)、[其他位置结论](smolvla-other-positions-conclusions-20261102.md)。 |
| 11-02至11-03 | wide72补采；G19错抓红被排除，11-03新green ep0补录313帧替代并归B02训练group | [数据优先v2计划更新](../plans/smolvla-data-first-v2-20261102.md)。旧原始错误条保留。 |
| 11-03 | v2本机从官方base重新20k训练；03:18启动，12:20:01 CST结束 | `E/smolvla-v2-local-training-20261103/training/{formal-start-verified.json,finished.txt,final-model-verified.json}`。报告/执行状态仍停step34，须以最终回执为完成证据。 |
| 11-03至11-04 | v3 balanced112导出与分层采样；正式在本机5060Ti完成8400步，11-03 18:38:36启动、11-04 00:10:04结束 | `E/smolvla-balanced-matpool-20261103/local-v3-run-bundle/{launch-receipt.json,formal-finished.txt,runtime-audit/final-verified.json}`。目录名含matpool，但正式训练地点是本机。 |
| 11-04 | v2与v3各12条C2/C3离线视频复核：11/12对7/12；v2新位置组合16条9/16 | [v2/v3比较](smolvla-v2-v3-real-comparison-20261104.md)、[新组合16](smolvla-v2-generalization16-results-20261104.md)。小样本回归，不是全网格可靠率。 |

## 2. v1/v2/v3数据构成、排除与划分

### v1：214 train / 52 validation

| 来源（共同前缀real-cube-bowl-） | split | 色 | episodes | frames |
|---|---|---|---:|---:|
| pilot-20261027 | train | G | 61 | 19803 |
| p2-green-20261030 | train | G | 10 | 3590 |
| p2-green-extra-clean-20261030 | train | G | 30 | 9898 |
| red-clean-20261028 | train | R | 92 | 24577 |
| p2-red-extra-20261030 | train | R | 21 | 5864 |
| adjacent-20261028 | validation | G | 32 | 11503 |
| p2-red-20261030 | validation | R | 20 | 6361 |

合计train214/63732（G101/33291，R113/30441）、val52/17864（G32/11503，R20/6361）；266/81596，双色总量各133。出处：[覆盖审计](smolvla-data-coverage-20261102.md)，逐条映射`E/smolvla-finetune-20261030/antzb-completed/data/build-01/episode-map.json`。

原green-extra ep2（第3条475帧）首次夹起失败、张开重抓而排除；green extra clean索引>=2对应原索引+1。旧红原ep10（第11条人工返回/重录）排除原条、保留重录；red clean索引>=10对应原索引+1。不要把1起的“第11条”写成0起ep11。原P0评估及策略失败rollout未当专家训练。clean来源仍追溯原folder/original episode，不能以clean目录制造新独立来源。

split按完整来源录制folder冻结；group/origin/完整数值轨迹hash跨split交集0，但不证明日期独立、视觉布局独立或无近似轨迹。全266轨迹身份及23派生文件SHA在11-02审计仍匹配；该审计新增全程人工审查0/266，新增初帧检查266/266，复用P2过程稀疏抽帧资格81/266，旧185沿用既有资格。

困难布局覆盖：G C2/R C3同格双色train/val均0但有近邻；G C3/R C2绿2条均val、红2条均train。近邻红指令validation也为空。不能因此声称该区域完全未见，不能将旧val两条搬进train“补齐”。早期文档“adjacent27/31、red66/84”使用录制序号；覆盖审计明确0起源索引adjacent26/30、red65/83。

### v2：保留v1 split，新增48 train / 24 validation

72条设计为3位置对(B1/B2、C2/C3、D3/D4)×2双色交换布局×2指令×2变化×3批次。B01/B02 train共48，B03完整validation24；同一批红绿folder共享group。正式wide plan的偏移是B01中心/+3mm、B02中心/−3mm、B03中心/+2mm，两块共同沿纸面列号方向移动，行轴和yaw保持0。此方案替代原36条中心/±3mm计划，不能把旧36命令写成已执行清单。出处`E/smolvla-wide-collection-20261102/plan.json`和[其他位置结论](smolvla-other-positions-conclusions-20261102.md)。

原72中G19=B02-green ep6错抓红排除；补录`real-cube-bowl-smolvla-v2-wide-g19-replacement-green-20261103:0`（313帧15.65秒）替代，归逻辑B02 group但保留独立physical source/origin/date；不能重复纳入两条。14源155文件SHA未变，实际338 episodes全数值身份、loader首尾、全部视频解码和train统计重算通过。最终批准manifest为`E/smolvla-v2-local-training-20261103/data/split-b02-corrected.json`，SHA `a695ba8e056e0f7aa0b75ea5580f6181ba3ea83c71002d717edce0692da499a4`。initial manifest仅历史。

| split | G episodes/frames | R episodes/frames | 合计episodes/frames |
|---|---:|---:|---:|
| train |125 / 39683|137 / 36197|262 / 75880|
| validation |44 / 14229|32 / 8916|76 / 23145|

直接出处`E/smolvla-v2-local-training-20261103/execution-status.json`的splits；训练完成另见final receipt。源不变不等于新视频做过全程逐帧人工审核，补录接受是完整性及视觉抽样审核。

### v3 balanced112：保留新48，旧214取64

旧64按16目标格×2指令色×2 episodes配额，旧G32/R32；保留v2新train48（G24/R24），合计112、G56/R56、31832帧。validation仍76/23145且原数值轨迹/视频字节保留，仅normalization reference改用v3训练stats。来源：[候选manifest](/data/work/so101-evidence/real-robot/smolvla-balanced-selection-20261103/candidate-manifest.json)、[视觉审核](/data/work/so101-evidence/real-robot/smolvla-balanced-selection-20261103/visual-audit/report.md)、[正式split](/data/work/so101-evidence/real-robot/smolvla-balanced-matpool-20261103/local-v3-run-bundle/evidence/split.json)。

选择只用old train，要求目标/干扰格均已知；优先有过程复核资格，再以固定布局双指令、颜色互换签名及干扰多样性优化。64旧条中16复用P2资格、48 legacy新增侧相机稀疏过程检查；新48复用已接受资格。48 legacy补看60–85%进程，未见错色/失败；不是全视频认证。pilot原ep0开头可见手部、5帧已退出，单独保留备注。新48格位依据计划名义格，G19补录也不认证毫米精确实摆。

v3不是“112条完全相同条件均衡”：训练采样为新48/旧64各50%，各层内红绿各50%，每色episode均匀，再在episode内frame均匀，带放回WeightedRandomSampler。每pass31840样本（原帧31832），正式四层实际采样67352/66944/67578/66926，见`runtime-audit/final-verified.json`。每条重复次数不同；总平均epochs接近不能视为同等优化进度。

## 3. 训练配置、结果与模型选择

三版均官方base重新开始，base revision `5e8d12a6e2975b0e5e5fce7c8caf47c371d257b6`、原权重SHA `7cd549ac2351fb069c0ddb3c34ad2d09cfc92b56a15dccdfc2e41467aaca01eb`；VLM/tokenizer revision `7b375e1b73b11138ff12fe22c8f2822d8fe03467`。6维state/action、20Hz、wrist→camera1、side→camera2，缺省camera3，图像640×480输入经补边512×512。双任务分别为 `Put the green cube into the paper bowl` / `Put the red cube into the paper bowl`。

基本optimizer：batch32、seed1000、AdamW lr1e-4、betas(.9,.95)、eps1e-8、weight_decay1e-10、clip10、cosine末端2.5e-6，augmentation关闭、AMP关闭、冻结vision/VLM、仅expert+state projection训练。v1文档称FP32但实际保留官方native BF16/F32混合参数；v2/v3在optimizer前显式.float()全参数F32，是另一项比较差异。

| 版本 | 地点/steps | 全量val/checkpoints | train stats SHA | 完成回执 |
|---|---|---|---|---|
|v1|antzb RTX5080 /20000|5000/10000/15000/20000，每次17864帧|`a894ea726894265d450f20acb9382be79a8372bbf6a7648a74735675720e5842`|`E/smolvla-finetune-20261030/antzb-completed/training/final-model-verified.json`|
|v2|本机5060Ti /20000|同4步，每次23145帧|`133e284d39c6eb05a96482961b06ec48a6c56fa7de4c26bd71869e2f74c45184`|`E/smolvla-v2-local-training-20261103/training/final-model-verified.json`|
|v3|本机5060Ti /8400|1000至8000每千步+8400，9次各23145帧|`7022c680952840da54e0b6631a2848f9476f394a692eadcbaaaea86862cbe540`|`E/smolvla-balanced-matpool-20261103/local-v3-run-bundle/runtime-audit/final-verified.json`|

v1/v2有效warmup666、decay20000；v3 warmup280、decay8400（preset1000/30000按预算缩放）。全局平均采样epochs v1约10.042，v2约8.434，v3约8.444。v1 mean update0.5789s、peak8781641216字节；v2 1.44386s、peak11326047744字节、末步loss0.08306472、gradnorm0.67524445，CPU严格重载450046176参数、全F32与processor train-stats匹配；GPU不同及dtype不同，不能用这些速度做纯算法比较。

v2真实batch32 smoke两次100步；group修正后二次权重与首次全量val probe SHA相同，155 trainable tensors均变、frozen未变，484测试通过。v3云准备README要求云端100-step smoke，但本地正式launch receipt明确实际前置local smoke=2步，并注明cloud100不要求本地；正式20步live observer观察155张量抽样参数均更新，最终8400 strict CPU reload+九次全val通过。不能把计划100写成v3实际100步。

以下native flow loss仅记录各版内部趋势，**跨不同stats不能直接比较**；也不等于去噪动作误差、选色正确率或抓取成功率。

|版本/step|G loss|R loss|
|---|---:|---:|
|v1 5000|0.285286|0.291308|
|v1 10000|0.370453|0.330686|
|v1 15000|0.439739|0.382604|
|v1 20000|0.444845|0.401601|
|v2 5000|0.264448|0.279259|
|v2 10000|0.323038|0.300139|
|v2 15000|0.416068|0.373745|
|v2 20000|0.462718|0.427509|
|v3 1000|0.310750|0.343645|
|v3 3000|0.300684|0.328466|
|v3 8400|0.448233|0.474540|

出处v1/v2 final-model-verified中的evaluation、v3 runtime-audit/result.json。loss按有效动作时间步加权，而不是固定chunk长度含padding平均。

v1已有608个固定观测预测证据：val body二阶差分5k/10k/15k/20k=5.213/2.875/2.024/1.771；对应匹配示范body MSE817.20/496.65/415.57/425.15。5k flow最低却动作最粗糙，因此改用20k为rollout候选。20k去噪步数10→20→50并未显著改善，平均计时190/259/551ms，不采用50。样本偏episode起点，非完整闭环结论。

v2的5k/20k原尺度比较已保存在`E/smolvla-balanced-matpool-20261103/baseline-comparison/comparison-summary.json`：76episode各12等距帧×3共同noise，逐维MAE/RMSE与首步误差，在各自反归一化后统计、排除padding、episode等权。不能混合前五关节与夹爪单位成一个scalar，也不能把这个v2-only比较说成v2/v3完成原尺度对照。

## 4. 同步→异步、连续性与诊断know-how

1. 同步每50步重新生成会阻塞约150ms，BF16只改善中位约4.4%，不能解决控制间隙。异步worker串行独占model/processor/CUDA，CPU执行线程按绝对20Hz消费；剩10步提前推理，返回后按request tick剔除过期前缀，直接替换未来队列。reset/pause增加generation，旧在途结果拒绝；空队列显式starved，不伪造hold，持续0.5秒退出，首块30秒timeout。
2. 20Hz供给只说明CPU动作可用，时间点早于串口发送；dataset时间戳frame_index/fps不是实际控制时钟。50步预测2.5秒，500ms预取不等于500ms观测延迟；原型稳态观测年龄中位1.1s、P99约2.1s，首块还包含冷加载。应先warmup再取得新观测。
3. 初期short blend使边界d1均值10.269→3.046/2.448（4/6tick），但相对hard最大偏离62.694/69.660°，且off-policy代理观测与新预测历史分叉，离线85.892°接缝不能冒充真实已发目标。约束project/gate候选均未过预先冻结留出stream，因此未部署。
4. 真机hard12的真实request/noise/chunk/install/output记录直接证明换块不连续：116边界d1均值5.833、max45.910，块内均值1.593；9次限幅都trial07。CPU目标45.91°、MAX_REL后goal、真实state单步变化是三件事；不能说机械臂一帧转45.91°。trial07最大边界是24.2秒撤回→再尝试，不能解释首次选错色。
5. 完整记录要捕获实际sample_noise而不新增随机调用，开关记录须输出及CPU/CUDA RNG逐元素相同；独立writer限item/bytes且满时丢日志计数，不能阻塞控制；complete=false保留所有失败语义。硬12有4874帧、130 predictions、128 installs、116后续边界，全部CPU输出与parquet逐元素一致。
6. 32次反事实原配对16/16 maxdiff0；布局1语言交换red−green pan绝对均值8.43°、布局2仅0.67°且方向混杂。说明存在语言响应且换位条件不稳，不能称完全忽略语言；pan未空间标定，不能代替正确目标判定。两个最大交接共享noise仍33–49°差，独立noise不足以解释它们；不能推广全部样本。
7. 单进程缓存只复用policy/pre/post，每条仍独立native context、camera/robot连接、scheduler、worker、recorder、generation，并在两条间reset和人工Enter。离线首次load13.247s、第二cache0.000138s，不代表完整真机节省。实际venv argv[0]、parser future-annotation、TerminalKeyListener非Thread清理三类启动/teardown缺陷均保留失败证据并修正。
8. normalization-reference.json只是审计引用，不会让LeRobot自动使用train stats；实际adapter/保存重载需证明pre-state/pre-action/post-action均用train统计。原始lerobot-train的task-tail拆分不能表达本项目整来源组留出，必须专用adapter；v2 sidecar/manifest counts不能用v1硬编码启动壳绕过。

## 5. 历次真机结果与边界

|批次|目标色入碗|错色/重要异常|结果来源|
|---|---|---|---|
|10-31 v1 5k同步2条|0/2，G0/1 R0/1|绿指令将红入碗，红抓取失败，均严重抖动|`E/smolvla-rollout-diagnosis-20261031/REPORT.md`|
|11-02 v1 20k异步相邻4条|2/4，G0/2 R2/2|绿两条碰推未夹起，换位绿首次集中C2；无starved/skipped|[四条](smolvla-paired-rollout-20261102.md)|
|11-02 v1 hard12|9/12，G3/6 R6/6|布局G C3/R C2绿色0/3；08/09错红入碗，07未稳定抓起；全程无starved/skipped|[数值](smolvla-hard-12trial-numeric-20261102.md)、既有visual目录|
|11-02 v1其他位置16|7/16，G3/8 R4/8|01/07/08/10错色入碗；15抓红悬碗未释放、超时后夹爪过载；09有29starved+7skipped|[结论](smolvla-other-positions-conclusions-20261102.md)|
|11-04 v2 C2/C3 12|11/12，G5/6 R6/6|稳定抓起11/11颜色对；07未稳定抓起，不算选色正确|[v2/v3](smolvla-v2-v3-real-comparison-20261104.md)|
|11-04 v3 C2/C3 12|7/12，G3/6 R4/6|11稳定抓起中7色对；06/08/09/12错色抓起，06/09/12错色入碗，08夹红碗空、退出时过载|同上|
|11-04 v2新组合16|9/16，G2/8 R7/8|03/12绿指令红入碗，5条未稳定抓起；1skipped，无starved|[新16](smolvla-v2-generalization16-results-20261104.md)|

v1其他位置按布局G B1/R B2：G0/2 R1/2；G B2/R B1：G2/2 R0/2；G D3/R D4：G1/2 R2/2；G D4/R D3：G0/2 R1/2。这促成覆盖三组位置的72示范，而不是继续只收C2/C3。

v2新组合布局G B2/R B3：4/4；G B3/R B2：2/4；G B1/R C3：1/4；G C3/R B1：2/4。不要把历史C2/C3的12条混入其16分母，也不要把已用于开发/补采决策的28条叫全新独立泛化集。

v2/v3同代码20Hz/horizon50/prefetch10/MAX_REL30、preflight均过，v3 warm约182ms、饥饿0，实际113条语言token均符合指令；目前不支持持续算力不足或任务文本传错解释。但初姿不同：v3 wrist_roll均值+4.89、夹爪−3.04（state标度，非确认物理单位），v3前8条夹爪1.16–2.52，续测9.18–12.24。原09–12来自独立续测包01–04。v3退步同时改变数据262→112、sampling、stats、steps20000→8400、LR schedule，且起姿/摆放/噪声有差，不能单归因“均衡策略不佳”。

## 6. 报告写作时须保留的矛盾和待核项

- v1 finetune文档止于排队、v2 report/execution-status止于step34；它们是历史快照，最终completion JSON及finished.txt已覆盖“尚未完成”的状态。不要静默改原文证据。
- v3 balanced-matpool README是云准备/100步门槛方案，实际本机launch前置smoke为2步；当前可证明8400正式、全val与严格重载，不能证明做过100步smoke。若总报告需要完整云生命周期，应另审MCP/上传/释放收据，本文件不将目录名当租机或云训练证据。
- 原36条补采、旧20秒自动reset草案、独立进程每条load均已被后续wide72/有限会话更新；日期旧文件含后续修正，须按执行收据断定实际状态。
- “同一base、FP32”描述有历史差异：v1 native mixed dtype，v2/v3显式all-F32。全量数据/训练位置/精度改变，v1→v2不是纯数据消融。
- 稀疏视觉复核、标签一致、视频完整、archive完整、execution returncode0都不能互相替代任务成功。原人工results.csv不少仍not_run/not_recorded；既有离线visual标签应标明来源，不能回填成新操作者验收。
- 新数据格位部分来自plan nominal，旧数据覆盖采用首帧检测；位置证据层级不同，精确布局成功率不能假定毫米级一致。preflight过只代表当前阈值，不证明相机/训练光照分布完全一致，wrist WB曾为auto。
- v2当前C2/C3明显好于旧v1同类回归，但小批次、日期/初姿/模型参数不同；不能说训练补采已证明因果，不能外推全网格可靠率。
- 本轮未重新核所有原始SHA、未逐视频视觉复验、未重跑训练/推理/测试。所列训练及数值结论是已有machine-readable回执与报告的交叉读取；需要独立复算时，应另建新输出而不覆盖历史证据。
