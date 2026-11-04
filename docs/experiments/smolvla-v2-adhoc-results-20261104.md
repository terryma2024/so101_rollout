# SmolVLA v2 ad-hoc 红绿测试结果（2026-11-04）

**自主目标色入碗：绿色7/10、红色3/10，合计10/20。** 红色另有1条经人工协助后入碗；包含协助的物理末态为红4/10、全部11/20，不能称为自主成功率。全部尝试保留，不删除协助条后改用9作主要分母。

这是助手对保存侧面视频的离线视觉复核，不是新增操作者逐条验收。原始视频、metadata和任何人工结果表保持只读。证据根：`/data/work/so101-evidence/real-robot/smolvla-v2-adhoc-analysis-20261104/`。

## 数据范围与编号

|组|dataset目录后缀|episodes|frames|自主入碗|
|---|---|---:|---:|---:|
|G1|eval-smolvla-v2-adhoc-green-20261104T100547|5|2384|3/5|
|G2|eval-smolvla-v2-adhoc-green-20261104T101133|5|1794|4/5|
|R|eval-smolvla-v2-adhoc-red-20261104T101548|10|4600|3/10，另1条协助|

目录均在 `/data/work/so101-datasets/`。两个绿色目录都有保存完备的episode元数据，合计10条；不能擅自把第一批当作启动测试丢弃。任务表绿色目录均green、红色目录red。表中G1-00/G2-00/R-00均为各目录episode_index=0，即本组第1条。

**人工协助的是R-01，即红色第2条、episode_index=1。** 约8–9秒人手进入工作区，之后红块被抓起并入碗。用户明确确认有触碰或协助，并在索引更正后再次确认对应这段。先前对话误称“第1条”已更正，不能把协助标记写到R-00。

## 逐条结果

|目录组 / 0起episode|本组第几条|指令|时长s|自主目标入碗|结果|
|---|---:|---|---:|---|---|
|G1-00|1|green|11.60|是|autonomous_success|
|G1-01|2|green|28.05|否|target_not_in_bowl|
|G1-02|3|green|29.80|否|target_not_in_bowl|
|G1-03|4|green|27.75|是|autonomous_success|
|G1-04|5|green|22.00|是|autonomous_success|
|G2-00|1|green|11.50|是|autonomous_success|
|G2-01|2|green|12.70|是|autonomous_success|
|G2-02|3|green|29.80|否|target_not_in_bowl|
|G2-03|4|green|12.50|是|autonomous_success|
|G2-04|5|green|23.20|是|autonomous_success|
|R-00|1|red|29.40|否|target_not_in_bowl|
|R-01|2|red|17.00|否|assisted_success|
|R-02|3|red|29.80|否|target_not_in_bowl|
|R-03|4|red|29.80|否|target_not_in_bowl|
|R-04|5|red|11.15|是|autonomous_success|
|R-05|6|red|29.80|否|target_not_in_bowl|
|R-06|7|red|11.55|是|autonomous_success|
|R-07|8|red|29.80|否|target_not_in_bowl|
|R-08|9|red|29.80|否|target_not_in_bowl|
|R-09|10|red|11.90|是|autonomous_success|

“target_not_in_bowl”只表示该条未完成指令色最终入碗，不一概等同于没有任何瞬时离桌。首个稳定抓起颜色、精确重试次数和未成功条的瞬时夹持，本报告没有全部完成逐帧编码，JSON明确为unknown；不据此编造一个100%的颜色正确率。

## 观察与解释

绿色失败为G1-01、G1-02、G2-02，均未完成目标入碗。成功中也有重试或较长过程，例如G1-03约27.75秒、G1-04约22秒、G2-04约23.2秒；终局成功不代表首次抓取就成功。

红色自主成功为R-04、R-06、R-09（人工顺序第5、7、10条）；R-01为协助成功；其余R-00、02、03、05、07、08未入碗。未成功片段可见反复向桌面方块接近、空爪向碗方向运行或退回后再尝试，支持继续排查接触对齐及抓空后仍执行运输阶段。没有看到错色块最终入碗，但“末态未错放”不证明每次选择正确，也不排除短暂错色接触。

本组自由摆放没有冻结精确格位、角度及位置分布，红绿10条不是同布局成对试验。随机20条红8/10、绿6/10，而本组红3/10、绿7/10，说明不同布局下的表现差异较大；不能简单认定模型始终偏红、也不能称颜色能力发生反转。没有模型更新，样本组成不同，不把两组比例变化解释为优化效果。若要确定位置因素，应在同一冻结布局分别测红绿并重复，记录初姿、夹爪和块朝向。

## 完整性、预检和时序

三个目录均有连续episode元数据，双相机640×480视频和数值帧，检查产物为integrity.json、episodes.json。总计8778个记录帧，两路视频对应各episode时间范围；不要把完整性当任务成功。

三次preflight分别为QNFOzH5z、avZDwfyB、dxpCyp2O（准确路径以diagnostics.json为准）；检查均passed，telemetry failed=null。遥测actions分别2384/1794/4600，与dataset帧数对应；全部20条有效输出约19.975–19.976Hz。starved_ticks和skipped_ticks均0。G1有1个stale result被丢弃，不等于过期动作已发送；其余两次为0。没有持续供给不足证据，但这些指标不量化机械抖动或实际串口延迟。

本报告仅以dataset任务、preflight与async telemetry核对；没有宣称完成random20那样完整推理archive的语言token解码、原始chunk/queue replay和逐元素输出审计。模型名来自本轮v2测试上下文及目录，不单靠目录名证明权重SHA。

## 图像审核与复现证据

先检查原视频640×480，再生成每ep首部、中部、尾部各两帧共六帧，10ep一张图。完整拼图保留，默认查看1153×1600预览：G_10ep_preview.jpg、R_10ep_preview.jpg。每episode另有1秒步长的timeline分段，长边不超过1600；R-01_timeline0.jpg显示协助片段。尺寸及帧索引见episodes.json、timeline_metadata.json；原图和原视频未改。

主Agent复核红绿overview及R-01时序，确认末态统计和协助索引。更细的首抓统计仍明确保留未知，不将稀疏抽帧包装成全程无遗漏事件检测。独立结果为visual_results.json；extract.py、timeline.py及write_report.py保存生成方法。当前分析未连接硬件、训练或调整相机。
