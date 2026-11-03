# SmolVLA 大分歧审计与受约束过渡（2026-11-02）

后续进展：已增加默认关闭的完整推理记录，保留原hard控制，详见[仪表验证与12条集中采集包](smolvla-hard-recording-20261102.md)。本文“未改runtime”指候选实验阶段，受约束控制至今未部署；文末4组×3条自动reset草案由新报告的12条独立进程方案替代。

本轮完成离线审计与484组新预测，**没有候选通过预先冻结的保留stream验收，因此不改runtime、不部署，不启动12条真机测试**。上轮真实记录确实测到换块不连续：4条记录在换块处的单步最大关节目标差均值5.51–11.83°，高于块内1.50–2.00°（见paired-rollout报告）。本轮原4/6tick融合的大偏离另包含预录观测与重放预测历史分叉，不能把离线85.89°伪交接当作真实已发目标；但约束后仍有明显目标阶跃，不能以硬切fallback称安全。

## 设计、冻结条件与范围

使用已批准的离线实验范围。工具`tools/smolvla_constrained_transition.py`、测试`tests/test_smolvla_constrained_transition.py`；大型证据目录`/data/work/so101-evidence/real-robot/smolvla-constrained-transition-20261102/`。沿用上轮4ep、48个request的真实安装tick关系及冻结观测，20k为主模型。模型路径`/data/work/so101-policies/real-smolvla-red-green-v1-20261030/checkpoints/020000/pretrained_model`，`model.safetensors` SHA256 `e96afce7f7bcb27237714421aa4f2e4360bc816ad3e89047363a0871ab0126bc`。所有模型文件SHA/config/processor映射及源archive SHA见`manifest.json`。

在生成新预测前，固定设计streams=1101/2202、保留streams=3303/4404、候选和阈值；报告没有看完保留结果再调参。每模式4streams×跨4ep共48requests=192chunks，两模式共384chunks：fixed对照在每stream全部request共享一个显式noise tensor；independent按SHA256(stream/episode/request)生成独立CPU Gaussian noise，全部策略共享exact raw chunks。同一stream的两模式是控制方案配对，不意味着每次request对应同一tensor。另在red ep1关键request40/80交叉比较5个noise条件（legacy1000+4新streams）、两模式、观测±2/4tick与零偏移，共100chunks；legacy1000两个模式有意重复作对照。计时另有1次重复性验证。

同一事件的过期前缀按installed-request剔除，4ep共177个原预测前缀动作/48个chunk；没有延迟安装或移动输出tick。原队列只剩连续5–6步，过渡不超过可用长度；不hold、不外推、不增减序列长度。夹爪始终直接取新chunk原值。

策略：hard；旧blend4/6；project4/6逐关节将原线性混合投影至“新预测±5°”与“相对当前记录state的绝对距离不超过新预测距离”的交集；gate4若窗口任一项违反同一约束，整窗硬切。最终步均回到原新预测，后续轨迹原样。state使用每tick记录state，是理想新鲜观测代理，不是已实现的runtime状态读取。

预冻结验收要求：每个保留episode×stream×noise模式的全序列、换块边界及窗口终点d2 p95/max均不劣于hard（1e-5数值容差）；相对新预测最大偏离≤5°；state逐关节距离不增加；夹爪逐元素相等；无hold/动作遗漏。降级/拒绝后边界仍出现>30°单步目标阶跃，也阻止进入真机。本轮5°与30°是保守工程筛选候选，**没有标定为物理安全阈值**。这个验收较严格，失败不证明所有受约束过渡均不可能，只表示本轮方案没有达到进入真机的依据。

## 原异常不是原真实chunk的复现

red ep1、legacy seed1000、request40时记录shoulder_lift=-99.82°，预测首步=-98.67°，起初相近。接下来旧预测保持折叠，而预录记录已经展开：

| tick | 旧chunk预测shoulder_lift | 记录state | 记录action |
|---|---:|---:|---:|
| 44 | -101.41 | -83.65 | -100.56 |
| 60 | -102.14 | -92.70 | -81.64 |
| 70 | -103.00 | -72.22 | -61.35 |
| 80 | -101.55 | -36.70 | -31.16 |
| 83 | -102.79 | -29.58 | -26.05 |
| 84 | -100.50 | -28.62 | -16.96 |

换块前重放实际输出=-102.79°，下一步新预测=-16.90°，硬切阶跃85.89°；旧future与新future首步差83.59°，4/6tick融合产生-79.60/-86.56°。旧future首步相对记录state最大体关节差71.88°，新prediction为15.94°。因此混合保留了已与预录观测不一致的历史；记录实际上一帧action=-26.05°，并没有发送重放上一帧-102.79°这一目标。旧chunk为本轮基于代理观测重推，并非原runtime保存的真实chunk，不能把这个例子当成原机器人必然出现85.89°交接。

`boundary-audit.json`为全部484个交接审计（legacy132+新352），保存raw old/new future、记录state/action、previous emitted、旧request state与首步预测、剩余queue、phase及人工接近窗口标记。4ep人工审阅窗口沿用既有结果：green0=5–7s、green1=11–13s、red0/red1=6–7s；阈值15的夹爪边沿±1s仅作事件代理，不能当真实接触标签。

## Noise与观测时序敏感性

同一个red ep1 tick84，legacy固定noise1000/2000/3000的旧肩预测为-100.50/+2.55/+10.66°，新肩预测为-16.90/-17.68/-20.30°：大分歧主要来自旧request40在展开临界阶段的预测变化。4个新fixed streams旧肩预测范围[-9.76,+3.83]°，独立noise旧肩预测[-33.25,+10.54]°；新肩预测分别[-20.55,-16.04]°与[-21.52,-15.81]°。新增样本中没有复现legacy1000在该边界的极端折叠值，但其他边界仍有很大阶跃，不能把旧极端样本删除后认定风险消失。

观测时移实验固定noise与队列时标，只同步替换state+双相机输入帧。legacy1000旧request40的对齐tick84预测，在frame36/38/40/42/44输入下为-103.53/-103.89/-100.50/+20.35/+23.82°；+2tick（100ms）改变120.85°，+4tick改变124.31°。新request80的对应肩预测为-26.42/-22.96/-16.90/-12.27/-14.45°。新4streams也显示旧request40强敏感：相对零时移的对齐body最大偏差最高111.14°，新request80最高11.29°。这是观测与noise交互敏感性的证据，**不是相机实际存在100ms时延的测量，也不能作因果贡献百分比分解**。正向时移是未来帧敏感性探针，不是可在线取得的观测。

新固定/独立模式全部176个交接各自old/new首步差p95=40.41/31.70°，max=90.49/74.46°；旧future相对state差p95=58.90/39.89°，新future=28.23/28.81°。独立noise没有在这4streams上统一加剧尖峰；小样本、不同noise序列不能推出其总体更安全。

## 保留streams结果

`d1[t]=max_body|a[t]-a[t-1]|`，`d2[t]=max_body|a[t]-2a[t-1]+a[t-2]|`；单位为°/sample和°/sample²，不是物理速度/加速度。边界d2含b与b+1。下表在每模式的4ep×2保留streams直接汇总样本，88个边界/176个边界d2；不平均各条分位数。

| noise模式 | 策略 | 边界d2 p95 / max | 全序列d2 p95 / max | 相对新预测max偏差 | 降级 / 硬切fallback |
|---|---|---:|---:|---:|---:|
| fixed | hard | 37.811 / 63.702 | 5.257 / 63.702 | 0.000 | 0 / 88 |
| fixed | blend4 | 8.779 / 16.564 | 4.590 / 19.922 | 47.138 | 0 / 0 |
| fixed | blend6 | 5.690 / 11.327 | 4.357 / 13.796 | 52.375 | 0 / 0 |
| fixed | project4 | 36.759 / 60.475 | 5.327 / 60.475 | 5.000 | 88 / 0 |
| fixed | project6 | 36.759 / 60.475 | 5.239 / 60.475 | 5.000 | 88 / 0 |
| fixed | gate4 | 37.811 / 63.702 | 5.257 / 63.702 | 0.000 | 88 / 88 |
| independent | hard | 33.369 / 46.443 | 5.291 / 46.443 | 0.000 | 0 / 88 |
| independent | blend4 | 7.731 / 12.390 | 4.579 / 15.842 | 32.245 | 0 / 0 |
| independent | blend6 | 5.608 / 10.044 | 4.444 / 15.253 | 35.828 | 0 / 0 |
| independent | project4 | 29.408 / 41.855 | 5.227 / 41.855 | 5.000 | 88 / 0 |
| independent | project6 | 29.408 / 41.855 | 5.143 / 41.855 | 5.000 | 88 / 0 |
| independent | gate4 | 33.369 / 46.443 | 5.291 / 46.443 | 0.000 | 88 / 88 |

表中hard的fallback=88表示策略本身硬切，不是运行异常。project在全部88个交接均触发至少一个关节/时刻投影；gate4的88/88窗口被拒绝，输出逐元素退化为hard，未取得有效平滑。旧blend4/6虽然降低d2，但最大偏离32–52°，且相对记录state逐关节最大距离增加28–50°，仍不满足目标偏离条件。project约束偏离至5°、state距离增加max=0，却保留大阶跃。其保留集fixed边界d1最大54.83°，independent=43.18°，hard分别59.66/47.75°。

不能只看合并表的改善：project4在4个单条保留序列的full_d2 p95变差；project6在5条变差。例：independent stream4404 green ep1，hard p95=5.2588，project4/6=5.3994/5.4109。gate没有分位指标劣化，但完全退化为hard。project4/6各仍有13个降级边界d1>30°，gate有15个，见`acceptance.json`的逐条tick/指标记录；这些尖峰是停止信号，不能称fallback安全。

保留边界旧queue共86个6tick、2个5tick（每模式），没有缺旧future的fallback。在人工接近窗口内每模式8个边界，hard边界d1 max=4.06/4.26°；最大的降级阶跃主要在展开或撤离阶段。每模式44/88边界落在夹爪边沿±1s代理内，不能仅因少数接近窗平稳就忽略其他阶段；夹爪未动也不代表腕臂轨迹无影响。

| noise模式 | 策略 | 过渡终点及后2步d2 max | 人工接近窗d2 p95 / max |
|---|---|---:|---:|
| fixed | hard | 63.702 | 2.883 / 4.444 |
| fixed | blend4 | 19.922 | 2.461 / 3.520 |
| fixed | blend6 | 13.796 | 2.428 / 3.525 |
| fixed | project4 | 10.261 | 2.485 / 3.520 |
| fixed | project6 | 15.043 | 2.461 / 3.525 |
| fixed | gate4 | 7.300 | 2.883 / 4.444 |
| independent | hard | 46.443 | 2.815 / 5.813 |
| independent | blend4 | 15.842 | 2.419 / 3.909 |
| independent | blend6 | 13.100 | 2.419 / 3.909 |
| independent | project4 | 15.842 | 2.532 / 4.282 |
| independent | project6 | 12.269 | 2.500 / 4.282 |
| independent | gate4 | 15.842 | 2.815 / 5.813 |

`sequence-metrics.json`和`pooled-metrics.json`保留完整d1/d2全序列、换块、±10tick、窗口末尾、人工接近窗p95/max，以及相对新prediction、previous action、记录state/action的距离统计。project6相对新预测每序列body MAE最大fixed=0.129°、independent=0.137°；只处理短交接窗口，不通过全程hold或压平轨迹取低d2。192条重放序列（32条输入序列×6策略），每个stream×模式的4ep合计1875tick，无遗漏，全部夹爪逐元素一致，闭合时标未延迟。expired prefix剔除不是新增遗漏。

## 复现、验证与限制

```bash
HF_HOME=/data/models/huggingface HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
/data/work/venvs/so101-smolvla-061/bin/python tools/smolvla_constrained_transition.py \
  --output /data/work/so101-evidence/real-robot/smolvla-constrained-transition-NEW --infer --analyze

# 只重放，不加载模型/GPU或连接硬件
/data/work/venvs/so101-smolvla-061/bin/python tools/smolvla_constrained_transition.py \
  --output /data/work/so101-evidence/real-robot/smolvla-constrained-transition-20261102 --analyze

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -c \
'import sys; sys.path.append("/data/work/venvs/so101-smolvla-061/lib/python3.12/site-packages"); import pytest; sys.exit(pytest.main(["-q"]))'
```

4组DRY_RUN命令均已实际展开验证，返回码全部0，无硬件访问（`plan-dry-run-validation.json`）。

新增7条测试覆盖偏离投影/state约束、gate接受与拒绝、无旧future、不hold/不外推、nonfinite、missing action、过期前缀错误、noise可复现/独立以及三个控制组与旧replay逐元素相同。全套418 passed（11.37s），证据`tests-final.log`。原scheduler reset/generation、过期前缀、慢推理及nonfinite既有测试仍通过；没有新runtime候选，所以不把它们称作新融合scheduler验证，也未运行候选真实backend smoke。

GPU运行前检查0%利用率、291MiB/16311MiB，RTX5060Ti；485次计时预测平均157.49ms，p95=159.13ms，max=480.12ms。独立noise重复预测maxdiff=0；时移零偏移重新解码与原/frozen预测maxdiff=0。完整episode CPU重放平均0.653ms、max=1.632ms，只是离线成本，不含真实scheduler、串口/相机。

所有源图先检查meta与ffprobe为640×480；不显示原图、不缩放模型输入。没有改runtime、连接相机/机械臂、发送动作、训练、commit或push；保留原dirty工作。重放观测是off-policy，state约束参照既有轨迹，不能验证闭环目标跟踪、选色、接触、碰撞或成功率。原runtime没有原始chunk和request相机快照，不能唯一识别noise、视觉时序、控制响应各自对旧运行的因果贡献。

下一实验优先在真实backend+录制观测、无硬件的条件下旁路保存每个request观测/时间戳、noise与raw chunk及换块old/new actions，验证记录不改变输出、调度或reset隔离。随后可由主审考虑12条仅增仪表、保持hard控制的基线诊断采集（不作为失败候选部署）；从真实运行首次获得原始chunk，避免off-policy反事实混淆。在独立样本上再评估更早prefetch/缩短开环跨度和大分歧处理，不能先放宽阈值启动融合真机。

## 12条集中监督测试方案（4组×3条，待主审）

当前0/12执行。受约束候选未通过，**没有候选真机执行命令**。用户希望一次性交付方案，用户自行集中完成后统一通知；不需要每条向agent确认。本节准备的是下一轮“仅增仪表、不改hard控制”的基线诊断矩阵，需主审先决定并补齐上节的无硬件仪表验证；本轮未实现原chunk记录，不能把当前launcher当成完整仪表采集方案直接启动。

`supervised-test-plan.json`含4组/12条映射，`planned-run-manifest.json`冻结当前模型SHA、代码SHA和hard参数（20Hz、50步chunk、prefetch10、MAX_REL30、30s/episode、20s reset）；`supervised-results.csv`为12行待填记录表。后续仪表代码完成时必须重新冻结其代码SHA及参数；不得冒充本轮已验收候选。

| 编号 | 组 | 布局 | 目标 | trial | dataset内episode |
|---|---:|---|---|---:|---:|
| 1 | 1 | G C2/R C3 | green | 1 | 0 |
| 2 | 1 | G C2/R C3 | green | 2 | 1 |
| 3 | 1 | G C2/R C3 | green | 3 | 2 |
| 4 | 2 | G C2/R C3 | red | 1 | 0 |
| 5 | 2 | G C2/R C3 | red | 2 | 1 |
| 6 | 2 | G C2/R C3 | red | 3 | 2 |
| 7 | 3 | R C2/G C3 | green | 1 | 0 |
| 8 | 3 | R C2/G C3 | green | 2 | 1 |
| 9 | 3 | R C2/G C3 | green | 3 | 2 |
| 10 | 4 | R C2/G C3 | red | 1 | 0 |
| 11 | 4 | R C2/G C3 | red | 2 | 1 |
| 12 | 4 | R C2/G C3 | red | 3 | 2 |

下列4条是**可复制的DRY_RUN展开检查**，不会接相机/机械臂；不是已批准的真机采集命令。每组新dataset各保存episode0/1/2，不能用旧dataset或RESUME混入往次结果。后续主审如选择基线仪表采集，应一次性交付完整live命令及步骤，不要求用户逐条确认。

```bash
POLICY=/data/work/so101-policies/real-smolvla-red-green-v1-20261030/checkpoints/020000/pretrained_model
# 组1: G C2/R C3, green, 3episodes
DRY_RUN=1 TASK="Put the green cube into the paper bowl" ./rollout_smolvla.sh eval-smolvla-baseline-instrumented-l1-green-20261102 3 "$POLICY"
# 组2: G C2/R C3, red, 3episodes
DRY_RUN=1 TASK="Put the red cube into the paper bowl" ./rollout_smolvla.sh eval-smolvla-baseline-instrumented-l1-red-20261102 3 "$POLICY"
# 组3: R C2/G C3, green, 3episodes
DRY_RUN=1 TASK="Put the green cube into the paper bowl" ./rollout_smolvla.sh eval-smolvla-baseline-instrumented-l2-green-20261102 3 "$POLICY"
# 组4: R C2/G C3, red, 3episodes
DRY_RUN=1 TASK="Put the red cube into the paper bowl" ./rollout_smolvla.sh eval-smolvla-baseline-instrumented-l2-red-20261102 3 "$POLICY"
```

恢复与键盘语义已核对当前安装的`lerobot/rollout/strategies/episodic.py`实现，而非凭假定：每episode开始reset异步engine并resume；默认`reset_to_initial_position=True`，无teleop时第1/2条结束后机器人先用1s自动返回本进程启动初姿，再进入20s reset窗；20s到自动开始下一条，不会无限等待用户。→可提前结束episode或reset窗；←会清除当前episode缓冲并重录，不应用来保留失败；Esc停止整组并保存当前缓冲。键盘控制依赖运行机器的pynput/桌面焦点，应在未来在场预检中验证，不把SSH终端按键当已验证的控制路径。

每组启动前摆到同一批准初姿、相同夹爪开度，记录首帧六关节和布局照片；四组之间也恢复相同初姿，不能用上一组末姿作为新startup姿态。每episode完成后先等待自动回初姿结束，再恢复方块C2/C3位置/方向、纸碗位置和夹爪状态，确认线缆与路径无干涉；不要在自动回位时伸手或强行拖动带力矩关节。20s不足则Esc停止本组，记录已完成episode映射，主审给出独立新dataset续测命令；不可任由下一条在未摆好时自动开始。若需要无限等待恢复，应先正式实现并验证，当前launcher不具备这一行为。

每次组启动launcher会先锁相机设置并作640×480、side对齐/光照预检，成功后才连接串口；操作者在场确认校准与初姿、空间、停止入口、Rerun显示。只在人工可立即停止的条件下运行；每条记录目标颜色、首次接触位置、夹起、入碗、碰推、异常展开/撤离、折叠无效持续、中止原因。异常时中止保留记录，不用←抹去失败，也不把失败动作直接作为专家数据。

结果位置：每组数据在`/data/work/so101-datasets/<上述dataset>/`，episode映射见表；每组启动终端打印`检查及异步遥测目录: /data/work/so101-evidence/real-robot/smolvla-rollout-preflight-XXXXXXXX/`，其中预检证据及`async-telemetry.json`须记录入CSV。新增仪表的request/raw chunk路径也必须出现在run manifest，当前未实现，不伪造路径。用户全部完成后一次性反馈四个dataset路径、四个预检/遥测目录与填好的结果表即可。
