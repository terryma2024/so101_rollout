# SmolVLA 固定观测诊断与换块连续性离线实验（2026-11-02）

本轮完成固定观测、显式相同初始噪声的15k/20k红绿指令交换，以及20k真实遥测时间对齐的新旧chunk重叠重放。短过渡能降低交接跳变，但局部偏离硬切轨迹最大约63–70°，因此**建议先继续诊断和约束大分歧交接，再安排监督真机实验**；不应仅按平滑指标直接部署。本轮没有连接机器人或相机、训练、改真实rollout策略、commit或push。

## 冻结输入与复现

工具：`tools/smolvla_offline_diagnosis.py`；数学/边界测试：`tests/test_smolvla_offline_diagnosis.py`。大型证据：`/data/work/so101-evidence/real-robot/smolvla-offline-continuity-20261102/`。

来源为`/data/work/so101-datasets/eval-smolvla-20k-async-{green,red}-r1-20261031`，各ep0/ep1；布局分别绿C2/红C3、红C2/绿C3。A的接近样本取既有人工审阅窗口起点，不取失败记录作专家目标。所有图像先以meta与ffprobe检查原尺寸640×480，再用FFmpeg libdav1d按帧号解码；不缩放源输入、不展示大图。输入保存为CHW float32 RGB/255；训练camera映射为wrist→camera1、side→camera2。视频每episode独立文件且from_timestamp=0，提取帧与frame_index相同。

| sample ID | 来源 | ep | 阶段 | episode内frame | dataset全局index |
|---|---|---:|---|---:|---:|
| 0 | green | 0 | 初始 | 0 | 0 |
| 3 | green | 0 | 接近5秒 | 100 | 100 |
| 16 | green | 1 | 初始 | 0 | 588 |
| 22 | green | 1 | 接近11秒 | 220 | 808 |
| 32 | red | 0 | 初始 | 0 | 0 |
| 35 | red | 0 | 接近6秒 | 120 | 120 |
| 40 | red | 1 | 初始 | 0 | 322 |
| 43 | red | 1 | 接近6秒 | 120 | 442 |

A：8样本×2checkpoint×2指令×3seed=96组；B：4ep共48个真实request×3seed=144组。两者复用18组，总计222个唯一chunk。B所有request_tick/installed_tick、源遥测路径和SHA在`episodes.json`，全部50个观测索引在`samples.json`。`observations.npz`冻结实际推理输入，`raw-predictions.npz`保存全部反归一化50×6预测，`old-new-overlaps.npz`保存各边界对齐的旧future/新future，`replay-sequences.npz`保存三策略完整序列及记录state/action。

模型根目录为`/data/work/so101-policies/real-smolvla-red-green-v1-20261030/checkpoints/`。

| checkpoint | model.safetensors SHA256 |
|---|---|
| 015000/pretrained_model | `2efa14c05d754f0494c82ffdc6b53b657fa396e779e8e3f4035f3499d42bcd19` |
| 020000/pretrained_model | `e96afce7f7bcb27237714421aa4f2e4360bc816ad3e89047363a0871ab0126bc` |

`model-manifest.json`记录解析路径、所有模型目录文件（含原config/processor）的SHA、有效config与camera映射。strict加载，float32/eval；种子1000、2000、3000通过CPU Generator显式生成`(1,chunk_size,max_action_dim)` Gaussian noise，再传`predict_action_chunk(noise=...)`，同seed在所有观测、指令、checkpoint间共享相同tensor；不依赖重置全局RNG碰巧相同。`initial-noise.npz`保存tensor，`verification.json`记录archive SHA并验证两checkpoint逐元素相同。20k sample0/green/seed1000重复预测maxdiff=0。

复现到一个新的输出目录：

```bash
HF_HOME=/data/models/huggingface HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
/data/work/venvs/so101-smolvla-061/bin/python tools/smolvla_offline_diagnosis.py \
  --output /data/work/so101-evidence/real-robot/smolvla-offline-continuity-NEW
```

正式运行RTX5060Ti GPU，75.71秒含11.8秒解码、两模型加载和保存；222次计时推理均值160.3ms、p50 158.3ms、p95 161.8ms、p99 177.4ms、最大455.0ms。纯推理累计约35.6秒；没有与其他模型作业争用GPU。首次尝试只在manifest的config序列化失败，未产生预测，改用dataclasses.asdict后正式重跑；失败输入保留于同级`-failed-config/`。

## A：语言与seed响应

下表为50步×前5关节的反归一化绝对差均值（°）。语言差为相同seed下红/绿配对差再平均；seed差为同指令下三组seed两两差再对双色平均。它们是响应幅度，不是正确动作误差或成功概率。

| 来源/ep/阶段 | 15k语言差 | 15k seed差 | 20k语言差 | 20k seed差 |
|---|---:|---:|---:|---:|
| green/0/初始 | 3.210 | 14.230 | 4.282 | 19.227 |
| green/0/接近 | 1.296 | 1.380 | 1.421 | 1.465 |
| green/1/初始 | 0.242 | 0.489 | 0.357 | 0.515 |
| green/1/接近 | 1.221 | 1.452 | 1.324 | 1.447 |
| red/0/初始 | 0.661 | 2.671 | 1.270 | 3.847 |
| red/0/接近 | 2.200 | 1.666 | 2.370 | 1.679 |
| red/1/初始 | 0.272 | 0.599 | 0.389 | 0.628 |
| red/1/接近 | 1.309 | 1.204 | 1.885 | 1.121 |

20k各样本语言差较15k大，但不能据此认定选色更好；green ep0初始seed差远大于语言差，20k反而更分散。green ep1初始两模型的pan末10步都约−1°，指令响应小，和本轮折叠启动困难的观察一致；单个2.5秒chunk不能证明之后七秒一定保持折叠。

pan可提示动作方向，但没有经标定的位置/颜色正确性。以20k接近输入前10步均值为例：green ep0绿指令三seed为2.57/3.21/3.08°，红为3.22/3.88/3.75°；red ep0绿为7.69/8.13/8.03°，红为8.03/8.59/8.51°。同一个布局却随来源姿态强烈变化，当前片段的pan保留了接近位置线索，不能证明语言把目标从C2切到C3。green ep1接近时两指令pan也相近，绿0.80/1.63/1.44°，红0.72/1.55/1.36°。

`language-metrics.json`另外保存前10、20–29及末10步的逐seed pan均值，完整轨迹在raw数组。后半chunk可能包含抓取后撤离，不能将末10步pan当作目标块位置；例如red ep0接近样本后半已预测大幅负pan。这里没有对失败rollout作专家GT评估，也不能据这些固定观测证明颜色选择正确。下一轮应在同一物理布局/姿态冻结成对成功示范，结合视觉接触位置判断，不能只依据语言差或flow loss选checkpoint。

## B：真实时序、原始chunk与短过渡

从真实遥测按绝对tick重建队列：第一个chunk在tick0安装；之后按installed_tick切换，将`installed_tick-request_tick`个新预测过期前缀剔除，保留原始request对齐。每个seed独立生成全部20k chunks，三个策略共享完全相同的原始预测，而非对已执行动作事后滤波。重放观测不会随融合改变。

过渡仅前5关节：第j步新预测权重`(j+1)/W`，第W步完全为新预测；夹爪始终严格取新chunk原值。旧future只有5–6步，4tick均可完整；6tick的132个交接中3个只能用5tick，其余6tick。窗口缩短至连续可用旧future长度；无旧future则硬切，绝不hold或外推。该fallback由单测覆盖。

定义`d1[t]=max_joint(abs(a[t]-a[t-1]))`、`d2[t]=max_joint(abs(a[t]-2a[t-1]+a[t-2]))`，只计前5关节，单位分别°/sample和°/sample²，不是物理速度/加速度。换块边界为新块首个输出tick；边界d2计t=b和b+1。表中分位数是对全部12条ep×seed的样本直接合并计算，非分位数平均。132个交接、264个边界d2、5601个全序列d2。完整逐episode/seed指标见`continuity-metrics.json`，合并口径见`pooled-metrics.json`。

| 指标 | 硬替换 | 4tick | 6tick（不足时5tick） |
|---|---:|---:|---:|
| 边界d1 mean | 10.269 | 3.046 | 2.448 |
| 边界d1 p50 | 5.211 | 1.465 | 1.424 |
| 边界d1 p95 | 36.385 | 10.147 | 8.062 |
| 边界d1 p99 | 74.625 | 21.733 | 15.070 |
| 边界d1 max | 85.892 | 24.199 | 18.484 |
| 边界d2 mean | 10.302 | 2.731 | 2.313 |
| 边界d2 p95 / p99 | 35.429 / 73.992 | 6.748 / 15.337 | 5.104 / 11.181 |
| 边界d2 max | 86.825 | 24.130 | 17.164 |
| 全序列d2 mean | 2.149 | 1.814 | 1.755 |
| 块内d2 mean | 1.745 | 1.768 | 1.728 |
| 边界±10tick d2 mean | 2.607 | 1.930 | 1.811 |
| 边界±10tick d1 max | 85.892 | 24.199 | 18.484 |
| 过渡终点/下一步d1 mean | 6.353 | 2.972 | 2.468 |
| 过渡终点/下一步d1 max | 85.892 | 20.234 | 17.830 |
| 过渡终点及后2步d2 max | 86.825 | 16.474 | 15.928 |

4tick/6tick在全部12条ep×seed均降低全序列d2。±10tick及过渡结束指标没有出现与原交接尖峰同量级的后移峰；不过4tick块内d2略升，不能称所有时刻更平滑。边界±10tick的d1 p95硬切5.964°、4tick6.164°、6tick6.197°，说明过渡分摊跳变仍会增加部分中等幅度目标步进。

以下误差是12条序列各自均值再等权平均，不是示范拟合质量或真实跟踪效果。

| 轨迹/预算检查 | 硬替换 | 4tick | 6tick |
|---|---:|---:|---:|
| 相对硬切前5关节MAE（°） | 0 | 0.159 | 0.270 |
| 相对硬切最大单关节偏离（°） | 0 | 62.694 | 69.660 |
| 与记录state MAE（°） | 3.200 | 3.186 | 3.176 |
| 与记录action MAE（°） | 2.497 | 2.594 | 2.669 |
| 与硬切夹爪最大差 | 0 | 0 | 0 |
| 完整episode CPU重放均值（ms） | 0.258 | 0.351 | 0.388 |
| 完整episode CPU重放最大（ms） | 0.333 | 0.464 | 0.498 |

夹爪全数组逐元素相等，阈值15的开合边沿计数也完全一致，未延迟夹爪闭合。该阈值仅是数值检查，不是接触事件。CPU重放预算不包含真实scheduler、相机、串口；运行时成本不能直接从此值保证。

**局部风险例子：**red ep1、seed1000、tick84的shoulder_lift：硬切−16.90°，记录state−28.62°、记录action−16.96°，4tick结果−79.60°、6tick−86.56°。这是旧chunk还在折叠方向、新chunk根据新的记录观测已转向的巨大分歧；平滑后的目标可能暂时更远离当前state，不能从全序列平均state误差略降推断它安全或跟踪更好。先保留同一套raw，诊断这些大分歧的来源/阶段，并比较带状态和目标偏离约束的过渡候选，再决定监督真机测试。6tick比4tick更平滑，却付出更大偏离；当前不据此选定部署窗口。

## 验证与限制

数学测试5项覆盖：过期前缀与tick对齐、前5关节权重及夹爪不变、旧future不足/缺失/无输出的处理、过渡结束尖峰及合并样本统计的覆盖。全套411 passed（11.32秒），命令与结果为：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -c \
'import sys; sys.path.append("/data/work/venvs/so101-smolvla-061/lib/python3.12/site-packages"); import pytest; sys.exit(pytest.main(["-q"]))'
```

关闭系统ROS pytest插件自动加载（系统插件缺lark）。仓库.venv本身缺av/pandas，第一次全套406 passed/4 failed，均在test_tools.py的这些依赖导入；直接换SmolVLA解释器又触发旧安装包的provenance/async import失败，见`tests-smolvla-env-failed.log`。最终保留repo解释器，仅临时append已有依赖路径，不安装或修改任何环境，411全通过；`tests-final.log`保存最终结果。raw完整性另确认222个50×6有限输出、noise配对相等及全部夹爪序列完全一致。

这是纯offline工具，没有复用或修改真实runtime scheduler，因此**本实验不验证reset/generation屏障、实时饥饿或真实发送**。既有scheduler测试在全套测试中仍通过，不能将其等同新融合runtime实现已验证。

真实遥测没有记录request时刻完整相机快照，本轮以request_tick对应数据集观测为明确可复现代理，保留request/installed时间关系；相机采集与记录时序可能有差，不能声称精确再现原运行原始chunks。记录中的20k模型也未冻结SHA，本轮仅比较上述精确冻结的本地15k/20k。本轮每个base seed在所有request复用同一个noise tensor，控制观测变化的随机混杂；它不复现原runtime各次request独立采样的随机序列，只有三个控制噪声条件，不能概括所有噪声情况。预测/融合都基于固定预录观测，机械臂不会因候选动作反馈改变，不能判断闭环跟踪、碰撞、颜色选择或抓取成功。记录action为限幅前目标，不是实际单帧机械运动。本轮结果支持继续研究连续性约束，同时继续成对布局/颜色的数据诊断，不支持无差别继续长训。
