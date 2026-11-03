# SmolVLA 数据覆盖与质量审计（2026-11-02）

**决定：保留旧7个来源组的冻结split作为回归基线；先补采36条独立批次示范，再验收并重组派生集。现有数据可用于重组对照，但不足以证明仅重组能解决这次双色位置混淆。** 36是首轮有界起点，不是理论最小值，也不保证训练成功。未修改源数据、相机或控制；未执行硬件动作、训练、上传。

证据根目录：[smolvla-data-coverage-20261102](/data/work/so101-evidence/real-robot/smolvla-data-coverage-20261102/)。工具：[audit_smolvla_coverage.py](../../tools/audit_smolvla_coverage.py)。266条逐episode明细在[episodes.csv](/data/work/so101-evidence/real-robot/smolvla-data-coverage-20261102/episodes.csv)，完整嵌套定位候选在[episodes.json](/data/work/so101-evidence/real-robot/smolvla-data-coverage-20261102/episodes.json)。所有未知保留unknown。

## 已核验来源与split

审计基于当前本机派生集，不以训练文档计数代替实际读取。独立读取全部data/meta parquet，重算266条numeric_digest并与冻结episode-map逐条相等；重算23个派生文件SHA256，全部匹配训练时冻结manifest，包括视频。train/validation的tasks表均为0→`Put the green cube into the paper bowl`，1→`Put the red cube into the paper bowl`，全部81596帧task_index与所属颜色一致。**这是标签与元数据一致性，不是266条都抓对颜色的证明。**

| 来源组（省略共同real-cube-bowl-前缀） | split | 指令色 | episodes | frames | 布局unknown |
|---|---|---|---:|---:|---:|
| pilot-20261027 | train | G | 61 | 19803 | 1 |
| p2-green-20261030 | train | G | 10 | 3590 | 0 |
| p2-green-extra-clean-20261030 | train | G | 30 | 9898 | 0 |
| red-clean-20261028 | train | R | 92 | 24577 | 1 |
| p2-red-extra-20261030 | train | R | 21 | 5864 | 0 |
| adjacent-20261028 | validation | G | 32 | 11503 | 0 |
| p2-red-20261030 | validation | R | 20 | 6361 | 0 |

合计train **214条/63732帧，G101/R113**；validation **52条/17864帧，G32/R20**。来源映射同时保留source_episode_index、original_episode_index、approved_episode_index和derived_episode_index；clean删除不能用清洗后索引直接查原采集表。旧red clean索引≥10的原索引加1；green extra clean索引≥2的原索引加1。原始拒绝示范未重新纳入。

精确追溯的冻结源是`smolvla-finetune-20261030/antzb-completed/data/build-01/{episode-map,split,dataset-files-sha256}.json`。本轮审计结果见[dataset-checks.json](/data/work/so101-evidence/real-robot/smolvla-data-coverage-20261102/dataset-checks.json)、[frozen-files-verification.json](/data/work/so101-evidence/real-robot/smolvla-data-coverage-20261102/frozen-files-verification.json)。未重新计算7个原始来源的全部文件SHA；当前派生文件字节一致及逐条轨迹一致不应被扩展成新的全来源视频验收。

## 指令色 × 目标格 × 干扰格

下表“同格”表示名义4cm网格标签相同，不表示两次摆放在毫米级一致。全量组合统计在[coverage.json](/data/work/so101-evidence/real-robot/smolvla-data-coverage-20261102/coverage.json)。

| 物理布局 | 指令 | train同格 | val同格 | train近邻 | val近邻 |
|---|---|---:|---:|---:|---:|
| G C2 / R C3 | G | 0 | 0 | 7 | 7 |
| G C2 / R C3 | R | 0 | 0 | 13 | 0 |
| G C3 / R C2 | G | 0 | 2 | 7 | 5 |
| G C3 / R C2 | R | 2 | 0 | 11 | 0 |

近邻为两种颜色分别到指定格的Manhattan距离≤1格，即每块可在原格或相邻正交格（4cm）；包含同格，计数不是新增独立样本。[near-neighbor-coverage.json](/data/work/so101-evidence/real-robot/smolvla-data-coverage-20261102/near-neighbor-coverage.json)保留全部命中origin。**邻近区域有数据，不能把同格零计数解释成该位置完全没见过。** 红指令在这两个近邻定义下validation均为0；原验证损失不能单独代表这两个困难布局的红指令表现。

G C3/R C2的4条可精确追到：

| split | 指令 | derived episode（0起） | 原始来源episode（0起） |
|---|---|---:|---|
| validation | G | 26 | adjacent-20261028:26 |
| validation | G | 30 | adjacent-20261028:30 |
| train | R | 165 | red-20261028:65 |
| train | R | 183 | red-20261028:83 |

因此“困难绿布局集中val”的怀疑得到局部证实：该名义布局的两条green示范都在val，red示范在train。当前12次实测为G C2/R C3双色各3/3、G C3/R C2绿0/3红3/3，与这个不平衡方向相容；**不能据此证明因果**，每单元仅3次，而且另一名义布局同格零计数仍能成功。

## 初帧定位、采集表和边界限制

本轮对266条侧相机首帧全部解码提取，先读取流宽高，均640×480；保留首帧副本，生成并查看14张1020×1320接触表，未连续加载原尺寸大图。细节复核只从640×480源帧裁剪放大，原图保留。[image-dimensions.json](/data/work/so101-evidence/real-robot/smolvla-data-coverage-20261102/image-dimensions.json)与[sheets/](/data/work/so101-evidence/real-robot/smolvla-data-coverage-20261102/sheets/)可复查。

位置证据优先级：pilot复用`full-r3/full-summary.json`中实际初帧反投影结果（61条）；adjacent与旧red复用既有初帧cell-check实际检测（32/93条，clean按原索引连接）。P2的81条以本次首帧r3标定投影16格HSV检测、颜色连通块质心最近格及接触表核对，**不直接用计划位置填实际位置**。计划表来自`tools/plans/p2-20261030.json`及各历史placement清单；计划和实际字段分开保存。

尚有2条布局unknown：pilot原索引4缺green检测；旧red原索引82的red检测不唯一。未根据计划或肉眼看起来“应在某格”强行回填。P2 red extra实际21条而计划20条，中后段出现顺序/重录或摆位差异，因此机械按计划行号映射不可靠。当前名义格与计划不一致计数为pilot4、green extra1、old red5、red extra14；其中包含unknown、毫米偏移导致最近格变化及录制顺序差异，**不等于24条示范失败或错抓**，不得据此批量剔除。

格标签是粗分类。投影检测受光照、侧面质心、遮挡和2cm高度假设影响；blob最近格距离门限17px仅为候选过滤，没有误差标定或near-cell置信区间，格边界附近可能换格。本轮没有把这些点声称为毫米精确位置。两条green困难val及两条red困难train初帧视觉和既有实际定位相互支持；零计数只指当前可辨识的名义格标签，unknown与格边界不能支持“绝对不存在”。补采应保存实际初帧、原位及±3mm变化，按真实摆放验收。

## 质量、动作与泄漏

本轮新增动作全程人工审查为**0/266**；新增初帧人工接触表检查为**266/266**。本轮没有对全部视频重新完整解码或逐帧人工播放。P2已有明确过程抽帧人工审查可复用**81/266（30.5%）**：green接受40条、red接受41条，均有双相机过程/末帧证据，目标入碗且干扰留桌，未发现已记录的错色。此为既有审查，不能写作本轮新看了81条完整视频。旧185条沿用既有接受资格；本轮未独立认证其完整动作颜色/抓取成功。

先前green extra第3条因重抓被拒绝；本集保持排除，原始数据保留。red旧第11条的人工返回/重录映射保持排除原条、保留重录。P2首次抓取成功在稀疏过程审查下普遍unknown，本清单全部保守标unknown；不能由末帧成功推导一次抓取成功率。可接受示范不意味着没有所有瞬间的人工干预，抽帧间隙仍有限制。

266条origin、完整numeric_sha256均全局唯一；group/origin/数值轨迹hash跨split交集均0。来源组没有跨split，clean没有伪造独立原始采集组。[leakage.json](/data/work/so101-evidence/real-robot/smolvla-data-coverage-20261102/leakage.json)记录检查。266张首帧JPEG还做了字节级重复检查；这不排除相似布局、同日光照或近似动作。**当前split是来源folder隔离，不能称作日期独立或视觉布局独立**。位置/颜色覆盖不平衡是真问题，但没有发现完全重复轨迹泄漏。

## 下一步决定与可执行缺口

不建议只把adjacent两条困难green搬进train：会拆来源批次并污染当前回归；若搬整个32条adjacent，验证会失去整个green组。现有7组可做整组重排对照，但无法创造G C2/R C3的同格双指令数据，也没有新独立同分布验证。因此先补采，再做train统计拟合与派生集导出。

| 单元 | 当前train同格 | 本轮新增train | 本轮新增val |
|---|---:|---:|---:|
| G C2/R C3，指令G | 0 | 6 | 3 |
| G C2/R C3，指令R | 0 | 6 | 3 |
| G C3/R C2，指令G | 0 | 6 | 3 |
| G C3/R C2，指令R | 2 | 6 | 3 |

采用3个独立摆放批次，每批包含4单元×3变化＝12条；变化为两块共同沿纸面列号方向−3/0/+3mm，保持两块相对关系。前2批24条train，第3批12条validation；每批内交错双色和布局，重录保留所属批次，不能为平衡再把同一批随机拆到train/val。按颜色分folder仍需以共同批次ID划分，不能把同一批双色folder视为独立拍摄组。具体采集清单和批次顺序以[独立补采包](smolvla-v2-collection-20261102.md)为准；本审计的collection-plan仅记录方案，不是训练可用manifest。

保留旧split并在全部新样本通过验收后追加，预计train **238（G113/R125）**，validation **64（G38/R26）**。这些是计划计数，尚无新采集数据。验收需初帧实际格/偏移、task文本、全过程目标色与最终结果、人工接触、抓取/重抓unknown或已证实标签、源数值hash和完整来源映射。拒绝记录保留，不静默用失败示范补足配额。

重组完成后重新拟合train-only normalization；新val复用train处理器。旧验证结果单独保留；新困难val按4单元分别报告，不只汇总loss。36样本通过后仍可能需要补采，下一轮是否扩大由4单元离线误差和独立真机评估决定，当前不预先宣称充分。

复跑使用新证据目录，旧证据不会覆盖：`/data/work/venvs/so101-smolvla-061/bin/python -m tools.audit_smolvla_coverage --evidence /data/work/so101-evidence/real-robot/smolvla-data-coverage-rerun-NEW`，再用相同`--evidence`运行仓库工具`python -m tools.finalize_smolvla_coverage`生成CSV/near汇总和质量范围标记。两工具均拒绝覆盖已完成的相应证据。`frozen-split-reference.json`仅封存现有引用，不是新派生导出验收。已验证工具可运行和266条哈希相等；没有启动训练。

工具整理后已在独立新目录`smolvla-data-coverage-reproduction-20261102`完成整套复跑，原证据未覆盖。episodes.csv、episodes.json、coverage、near-neighbor、source-summary、leakage及initial-image-duplicates这7项产物与原证据逐字节一致；两工具编译检查通过。[复跑核验](/data/work/so101-evidence/real-robot/smolvla-data-coverage-reproduction-20261102/reproduction-verification.json)。必要汇总脚本现位于仓库[finalize_smolvla_coverage.py](../../tools/finalize_smolvla_coverage.py)，不依赖证据目录脚本副本。
