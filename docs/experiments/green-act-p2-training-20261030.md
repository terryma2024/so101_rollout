# 2026-10-30 绿色 ACT：P2 数据审查与训练交接

用户授权：检查今日41条绿色示范，将可用部分与旧训练数据组合，在 antzb 训练新版绿色 ACT。

审查结论为40条接受、1条排除。两批原始数据共41条13963帧，视频完整解码与数据逐条对应，索引、时间戳、有限数值及任务标签通过。过程抽样复核绿色入碗、红色留桌；并非逐帧人工审查，不将所有接受记录标成已证明首次抓取成功。

排除 `real-cube-bowl-p2-green-extra-20261030` 的 `episode_index=2`（录制第3条，475帧）：首次闭夹未搬起，随后张开重抓。第6、12条手臂只出现在桌前缘外围，未见物体/碗/机械臂接触。第24条接近时推转目标并调整，首次闭夹后抓起，接受并保留备注。全部原始记录保留。

训练来源：旧版 REAL-ACT-002 的 `real-cube-bowl-merged-20261028`（93条31306帧）＋今日 green 批次全部10条3590帧＋green-extra 批次30条9898帧。目标合并集 `real-cube-bowl-green-p2-merged-20261030`：133条44794帧，20fps，双相机640×480，单任务 `Put the green cube into the paper bowl`。不含P0评估或红色示范。

训练复用旧版完整配置，仅变更 dataset.repo_id、dataset.root、job_name、output_dir。ACT 从头训练（保留相同ImageNet预训练ResNet18骨干），batch 8，100000步，chunk_size/n_action_steps 100，学习率1e-5，seed 1000，8 workers，图像增强开启，每20000步保存，不上传Hub。

模型目标路径（antzb）：`/data/work/so101-policies/real-act-green-p2-20261030`。

完整审计：`/data/work/so101-evidence/real-robot/green-p2-audit-20261030/summary.md`、`episode-decisions.csv`、`accepted-rejected-map.json`。训练交接证据：`/data/work/so101-evidence/real-robot/train-real-act-green-p2-20261030/`，含配置差异、源文件SHA256、合并脚本和验证结果、传输校验及持久运行脚本。启动状态以该目录的时间、PID、日志和退出码为准。

合并兼容修复：旧93条只有 `meta/episodes/chunk-000/file-000.parquet`，其中78条自指针仍带有旧file_index 1/2/3。使用独立复制的派生视图，仅改真实元数据文件位置后再调用官方aggregate。官方聚合的旧float32数值统计存在精度偏差，因此以接受集float64输入重算全部数值特征的逐episode及全局统计，图像统计仍用官方episode摘要。官方删除extra第3条会重编码受影响的视频文件；数值轨迹保持逐值相等。

合并验证通过：133条44794帧数值逐值相等；全部5个视频文件完整解码并验证逐条时间区间；实际dataset loader读取全部266个episode首尾索引通过。原始30个文件SHA256与文件集合均未变。2026-10-30 10:49 CST完成传输，远端10个文件成员与SHA256全部一致；canonical JSON树摘要 `106a7efbd177e8bb99c10e551ab54b69a775ee85b8b07246598ad8b25d822f7a`。

antzb训练已于2026-10-30 10:51:16 CST持久启动，运行shell PID 4016728。主Agent独立SSH确认10:51:51达到step200，loss 6.792（l1 0.747、KL 0.604），学习率1e-5，GPU约5480MiB、89%利用率；无退出码标记，进程仍运行。这只证明启动和早期训练正常，训练尚未完成，后续以远端train.log、exit_code.txt和checkpoints为准。计划每20000步保存，100000步结束。
