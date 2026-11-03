# SmolVLA 12条真实推理记录数值审计（2026-11-02）

**12条采集均有效，20Hz没有断流；真实换块目标不连续得到直接证实，但不能用换块抖动解释全部选色错误。** 本轮审计使用真实保存的request、noise、chunk、安装queue与CPU输出，不再从预录观测重造历史。主审汇总的视觉初判：01–06和10–12正确入碗（9/12），07推红未夹起，08/09红入碗但目标应为绿；布局2的green均未正确入碗；07腕视初次爪靠近绿再红，不能把侧视C2红运动直接等同首次红接触；选色/位置偏好须与连续性分别诊断，最终逐条视觉结论由视觉报告负责。本报告不凭关节轨迹填成功标签，原`results.csv`的not_run空表保持原样。

## 完整性、模型与运行条件

源执行包`/data/work/so101-evidence/real-robot/smolvla-hard-recording-20261102/collection-package/`；最终分析证据`/data/work/so101-evidence/real-robot/smolvla-hard-12trial-analysis-20261102/final/`；只读分析工具`tools/analyze_smolvla_recorded_trials.py`。

- 12个execution均returncode=0；12个记录status均complete=true、dropped=0、errors=[]，文件编号连续、accepted=written=文件数。
- 共4874帧、130个实际request/noise/完整50×6 chunk、128次安装、116次后续换块。两次episode结束前已完成但尚未安装的预测也保留，130个预测不等于130个已执行块。
- 全部raw→trimmed future对齐、旧queue重建及实际CPU输出逐元素一致；全部4874个CPU输出与dataset action逐元素一致。所有request snapshot的state与其request_tick对应的dataset state逐元素一致，包括首请求，未出现上轮代理观测的历史重放错位。
- 全部12条preflight和side alignment通过；相同20k解析路径`/data/work/so101-policies/real-smolvla-red-green-v1-20261030/checkpoints/020000/pretrained_model`，weights SHA256 `e96afce7f7bcb27237714421aa4f2e4360bc816ad3e89047363a0871ab0126bc`，全部runtime代码manifest一致。参数均hard、20Hz、horizon50、prefetch10、MAX_REL30。
- 全部无starved/skipped/stale；安装过期前缀4tick有114个、5tick有2个，连续旧future分别6tick/5tick。4–5tick是新预测安装年龄，不是实测相机曝光延迟。
- side预检dx约−1.53至−0.99px、dy−0.99至−0.35px、rotation约−1.17至−0.99°，inliers47–66；背景亮度相对预检参考delta7.48–10.29、纸碗7.82–9.92，均通过当前门槛。预检通过不能证明双色训练/运行颜色分布一致，校色分析另行进行。

12次起姿的前5关节peak-to-peak为[2.46,0.35,1.23,0.26,2.99]°，夹爪1.43个归一化单位；并非逐元素完全相同的初姿。关节单位按当前use_degrees=True解释前5关节为°；夹爪为0–100归一化值。

## 每条运行与换块指标

`d1[t]=max_body|a[t]-a[t-1]|`，`d2[t]=max_body|a[t]-2a[t-1]+a[t-2]|`。a为真实后端CPU目标，尚未经过机器人内部max-relative限制/串口发送；不是机械运动或速度/加速度。边界d2包含b和b+1，合并分位数直接合并样本，不平均每条分位数。

| ID | 布局/指令 | 帧数 | Hz | 换块数 | 边界d1 mean / max | 块内d1 mean | 限幅告警 |
|---|---|---:|---:|---:|---:|---:|---:|
| 01 | G C2/R C3 / green | 537 | 19.975 | 13 | 5.51 / 24.75 | 1.51 | 0 |
| 02 | G C2/R C3 / green | 369 | 19.975 | 9 | 3.32 / 9.63 | 1.42 | 0 |
| 03 | G C2/R C3 / green | 328 | 19.976 | 8 | 6.98 / 23.11 | 1.58 | 0 |
| 04 | G C2/R C3 / red | 402 | 19.975 | 9 | 8.13 / 31.05 | 1.90 | 0 |
| 05 | G C2/R C3 / red | 262 | 19.975 | 6 | 4.76 / 7.11 | 1.92 | 0 |
| 06 | G C2/R C3 / red | 292 | 19.975 | 7 | 9.06 / 26.39 | 1.96 | 0 |
| 07 | R C2/G C3 / green | 573 | 19.975 | 14 | 10.86 / 45.91 | 1.75 | 9 |
| 08 | R C2/G C3 / green | 573 | 19.976 | 14 | 3.75 / 19.07 | 1.39 | 0 |
| 09 | R C2/G C3 / green | 402 | 19.975 | 9 | 4.54 / 18.31 | 1.48 | 0 |
| 10 | R C2/G C3 / red | 294 | 19.976 | 7 | 4.45 / 14.90 | 1.68 | 0 |
| 11 | R C2/G C3 / red | 467 | 19.975 | 11 | 3.19 / 19.26 | 1.20 | 0 |
| 12 | R C2/G C3 / red | 375 | 19.976 | 9 | 4.73 / 13.06 | 1.64 | 0 |

每条有效输出覆盖约13.05–28.60秒，长度不强行补齐30秒；episode配置是最长30秒，启动等待、用户提前结束均可能影响有效帧长，本报告不据长度反推是否成功。各条间隔p99约50.20–51.07ms、全局最大53.02ms；热推理p95每条186.52–204.74ms，最大214.04ms。输出频率19.975–19.976Hz，当前证据不支持“推理断流导致这些失败”。

| 合并指标 | mean | p95 | max |
|---|---:|---:|---:|
| 换块d1（116样本） | 5.833 | 21.273 | 45.910 |
| 块内d1（4746样本） | 1.593 | 5.010 | 11.175 |
| 换块d2（232样本） | 6.211 | 21.823 | 47.056 |
| 块内d2（4618样本） | 1.641 | 4.061 | 10.746 |
| 全序列d2 | 1.860 | 4.679 | 47.056 |
| CPU目标与当前state最大body距离 | 5.065 | 15.685 | 44.048 |
| 实际记录state单步变化 | 1.147 | 4.484 | 9.231 |

这是实际运行中的target discontinuity，不是上轮off-policy重放带出的85.89°伪交接；但并非每个换块都大跳。只有2个边界d1>30°，7个>20°，最大块内d1=11.18°。不能把CPU目标的45.91°阶跃称为机械臂瞬间转动45.91°。

## 两个关键真实交接与9次限幅

**trial07，布局R C2/G C3，green，tick484/24.2s：**shoulder_lift上一CPU输出−87.742°，旧future同tick−89.649°，新目标−41.832°，构成真实CPU阶跃45.910°；记录当前state=−82.681°。old/new同tick差47.816°，旧future相对state最大body差6.967°，新目标为41.324°。这里旧future仍贴近真实记录，而新chunk改变了阶段；不能套用上轮“旧预测早已脱离记录”的解释。

旧request440的state lift=+25.714°，new request480为−73.099°，安装tick484已−82.681°；从旧观测到安装已有2.2秒真实运动。新观测至安装0.2秒又改变9.58°body角。因此模型是在不同状态/图像与不同noise上切换预测，长预测跨度与新观测阶段判断都值得检查，不能只归咎noise。

终端实际记录MAX_REL30的限幅：tick484 lift原目标−41.832→实际限幅goal−52.857，elbow28.786→40.198。相对上一帧lift目标−87.742，局部限幅后goal差约34.885°，仍不能当机械运动；当前记录state单步body max为4.132°。机器人限幅采用发送前额外sync_read，不能直接用早一点的dataset state计算精确发送目标。报告引用的是官方send_action的实际日志值。

**trial04，布局G C2/R C3，red，tick164/8.2s：**pan上一目标−24.699→新目标+6.351°，CPU阶跃31.050°；当前state pan=−20.264°，oldfuture pan=−26.468°，旧future相对state body max6.204°，新目标26.614°；该条没有MAX_REL告警。视觉初判此条最终正确入碗但有重试，说明大交接与最终选色正确可以同时存在，不能把选色与平滑性合并成一个问题。

主审已查看trial07 side 15–28s contact sheet：21–24s折叠撤回、25s再展开，因此24.2s最大边界处于撤回→再尝试转换，并非首次选错。不能把该晚期大边界解释为首次错色的原因。

trial07另在tick284/14.2s有27.261°肩阶跃，夹爪目标4.46→23.63；tick484夹爪1.83→26.50，均需要视觉确认是在撤回、重新接近还是失配尝试。本报告不把夹爪阈值当接触标签。

9次限幅全部属于trial07，精确匹配到tick285/286/287及484/485/486/487/488/489；其它11条0次。`clamp-events.json`保存逐关节original/safe goal，全部通过原目标浮点值唯一匹配对应CPU输出。没有通过把限幅前目标直接当实际发送来夸大风险；现有日志也不是所有电机原始bus command的完整记录。

## 选色/位置偏好与noise：已知和未知

实际130个noise tensor hash全部不同，相邻request noise余弦均值0.00054、范围约−0.0923至+0.0529；确认真实运行没有上轮“每request复用固定noise”的控制条件。不同hash与低相关不等于已证明统计独立，更不能据此分解失败原因。

同布局/同指令初始chunk也有不同展开速度：布局2 green三次首chunk末10步lift均值为−103.52/−38.73/−97.22°；实际首次state lift超过−20°分别在3.55/2.80/4.50s。布局1 green为5.10/5.00/3.20s。相机观测、起姿和noise都同时变化，不能将这些差异全算作noise。

为便于视觉定位，数值记录了首次state lift>20°后20帧的pan中位数，**仅是数值锚点，不是标定后的C2/C3分类器**：

| ID | 布局/目标 | 首次lift>20°时刻 | 其后1s pan中位数 |
|---|---|---:|---:|
| 01 | G C2/R C3 / green | 8.20s | 4.31° |
| 02 | G C2/R C3 / green | 7.10s | 5.14° |
| 03 | G C2/R C3 / green | 5.30s | 3.38° |
| 04 | G C2/R C3 / red | 4.95s | 7.34° |
| 05 | G C2/R C3 / red | 4.95s | 7.87° |
| 06 | G C2/R C3 / red | 5.50s | 7.78° |
| 07 | R C2/G C3 / green | 5.75s | 5.58° |
| 08 | R C2/G C3 / green | 5.75s | 3.34° |
| 09 | R C2/G C3 / green | 6.70s | 3.21° |
| 10 | R C2/G C3 / red | 5.00s | 0.92° |
| 11 | R C2/G C3 / red | 4.00s | 2.77° |
| 12 | R C2/G C3 / red | 4.50s | 1.19° |

布局1 red的该锚点pan约7.34–7.87°，布局2 red约0.92–2.77°，存在随布局改变位置的迹象；green在布局2约3.21/3.34/5.58°，并未稳定呈现red在布局1接近C3时的分支。结合视觉初判08/09错误将C2红入碗，07未成功且首次接触仍有视角不确定性，支持**green对换位后的目标位置条件不稳**这一待验证问题。不能仅从pan等于某值认定选色，更不能用换块抖动解释发生在首次接近方向上的系统性错位。

## 最小下一步离线验证（有限矩阵，不部署）

1. **优先验证颜色/位置条件，固定12个输入点。** 从每条视频首次触物之前选择最近的1个真实request，沿用原state、双图与实际noise；重推原指令作精确复现，再只交换green/red指令，共24次预测。按布局分别比较早期接近轨迹分支，并联合视觉目标区域判读；不能用单关节pan阈值替代选色。12个点/时间窗在看预测前冻结，保留一部分试次做验证，不因结果调整样本。
2. **另做2个最大真实交接的noise交叉。** trial07 tick484与trial04 tick164，各用old/new两份实际观测×old/new两份实际noise，共8次预测（含原配对复现）。old预测按其原horizon index44、new按index4比较同一绝对tick；这可分离同观测下noise变化的效应，但“更换观测”同时改变有效预测跨度，不能宣称纯相机延迟因果。总计最多32次预测，无新策略搜索、无硬件。
3. **再决定数据/控制方向。** 若同obs/noise交换指令仍不改变目标分支，优先检查green-C3成功示范覆盖、布局/颜色共现与标注；若语言响应有但C3精度不够，单独处理抓取/视觉位置误差。连续性应在真实raw交接上评估，允许把晚期重试交接与首次接近分开，不部署之前未通过的blend/project/gate；不直接长训或把失败作为专家样本。

主审授权的32次有限反事实已另行完成，见[固定输入反事实报告](smolvla-12trial-counterfactual-20261102.md)；本报告上述数值表仍仅使用真实运行记录。按用户要求，此有限任务保存后即停止，不继续自动实验。本轮数值审计，未启动训练、未发硬件动作、未修改原dataset/recording/结果表。视觉结论与校色结论由相应独立报告补齐。

## 复现与证据

```bash
PYTHONPATH=src:. /data/work/venvs/so101-smolvla-061/bin/python tools/analyze_smolvla_recorded_trials.py \
  --output /data/work/so101-evidence/real-robot/smolvla-hard-12trial-analysis-NEW
```

脚本只读源目录，输出必须是新目录。实际12条已完整运行全部assert：归档文件连续/complete、request↔snapshot↔inference字段、有限50×6 raw、raw→install、queue→CPU、CPU→dataset、预检与模型/代码一致、终端限幅原值唯一匹配。`source-sha256.json`冻结全部使用的原archive/数据parquet/预检/遥测/终端log与execution；`recorded-sequences-and-chunks.npz`保存可复查的完整实际序列和raw chunks；`trials.json`、`boundaries.json`、`pooled.json`、`noise.json`与`verification.json`保留逐条与汇总口径。未运行模型或GPU，本轮只做CPU数值读验。
