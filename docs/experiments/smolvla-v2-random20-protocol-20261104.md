# v2 随机位置20例测试方案

本轮供操作者亲自测试，不自动启动机械臂。使用v2 final20k，checkpoint路径和SHA256沿用既有16例包。独立输出目录为 `/data/work/so101-evidence/real-robot/smolvla-v2-random20-20261104/collection-package`；原16例、24例包和全部历史数据保留。

抽样域为已实际测试的七个格中心：B1、B2、B3、C2、C3、D3、D4。列偏移、行偏移均为0 mm，角度0°；碗、纸垫、相机、灯光及批准初姿固定。七格依据包括原C2/C3基线、generalization16的B2/B3与B1/C3、other-positions的D3/D4实测；这不代表每个新组合均已验证安全或成功，每条仍需原有预检和操作者确认。

`tools/prepare_smolvla_v2_random20.py` 固定seed=20261104，按上述格列表构造42种两块不同格的有序双色布局，`random.Random(seed).sample(..., 20)`无放回抽取20种不同布局，再用同一随机数流打乱红绿各10条目标指令。没有同布局双色配对或重复测试。本轮估计范围仅为这七格离散域，在平衡目标颜色条件下的描述性表现；不是全工作区连续均匀iid测试，也不能用20次证明总体可靠率。

生成脚本拒绝覆盖，校验模型权重SHA，并冻结输入哈希。沿用原persistent launcher和hard async参数：20Hz、horizon50、prefetch10、MAX_REL30，每条最长30秒，整批模型只加载一次，每条独立新dataset episode0；不增加runtime行为。计划、指令文档和单页20条PDF顺序相同：左列01-10向下，再右列11-20向下。每卡图位于右侧；本轮没有非标准角度或偏移。

```bash
# 仅首次生成；目录已存在时拒绝覆盖
python3 tools/prepare_smolvla_v2_random20.py

# 仅显示计划，不接设备
python3 /data/work/so101-evidence/real-robot/smolvla-v2-random20-20261104/collection-package/collect.py

# 操作者在场，本地前台一次执行完整批次
python3 /data/work/so101-evidence/real-robot/smolvla-v2-random20-20261104/collection-package/collect.py --execute
```

操作者每条确认恢复双色布局、空碗和批准初姿后按Enter。等正常回位及断连后再伸手。→结束当前条；Esc停止本轮并保留当前条；Ctrl-C结束整包；不要用←丢弃失败重录。安全异常及时停止并保留失败，不能盲目续跑。仅条间q正常退出、前序完整回执齐全且后续路径全新时，才按包内说明使用 `--execute --start-trial N` 恢复。

结果分别填写任意色稳定抓起、首次稳定抓起颜色及其是否正确、整条是否曾稳定抓起正确色、正确目标最终入碗。稳定抓起须明确离桌且由夹爪持续持住；接触、推块或夹空不能算。报告任意色稳定抓起/全部尝试、正确色稳定抓起/全部尝试、正确入碗/全部尝试，另报首次稳定抓起颜色正确/有首次稳定抓起的尝试及无抓起数。全批完成时分母20、每色10；所有失败、错色、安全停止保留，unknown单列。提前停止另报已开始数和未执行数，不将未执行标为完成，不以补跑替代失败，不与历史批次合并成功率。

生成时无真机执行；CSV全为not_run。PDF为一页A4，已用Poppler渲染成1132×1600预览，视觉核对20条顺序、布局、文字及无裁切；原2480×3508图保留。当前环境沿用既有Pillow PDF生成方式，无新增依赖。
