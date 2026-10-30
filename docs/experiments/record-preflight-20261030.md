# 2026-10-30：采集启动自动检查

> 以下为早期独立SIFT方案的历史记录，位置判定及其测试结论已被同日修复替代。当前要求见 [位置判定统一修复](record-preflight-align-unification-20261030.md) 与 README。

用户要求已实现：每次启动 record.sh，在相机参数锁定后、record_viz连接机械臂之前检查光照与侧面视角。检查失败、异常、超时或相机参数锁定失败时提示 `[y/N]`；只有独立输入 y/Y 才继续，其余输入和EOF取消。原补采命令与数据目录保持一致。

实现：`src/so101_rollout/camera/preflight.py`、`scripts/record.sh`；配置 `config/preflight.json`，参考图 `config/preflight/side-reference.png` 来自本次人工检查通过的640×480画面，SHA256在配置中。固定背景和纸张分别检查，排除方块/碗/机械臂；腕部只检查光照。参数是工程初值，可调，基准不会自动更新。遮挡、匹配不足会要求人工判断。

完整实现/审查/测试证据目录：
`/data/work/so101-evidence/real-robot/record-preflight-implementation/`

- 独立审查最终 Spec PASS / Quality PASS，报告 `review-report.md`。审核发现的覆盖率定义已修正为凸包与ROI交集占比。
- 最终全套300 passed in 2.95s，证据 `verified-final-pyxbpvid/`，8 workers；TMPDIR/TMP/TEMP位于该目录NVMe tmp，保存JUnit、完整控制台及worker临时目录证明。
- 最终真实camera-only检查通过：`/data/work/so101-evidence/real-robot/record-preflight-b_d1vl_g/result.json`。两路各40帧；背景角点最大位移约0.135px，纸张约0.312px。
- 只重装real运行环境的so101-rollout项目wheel，不升级依赖。wheel位于证据目录 `wheel-final/`，SHA256与安装代码验证见 `runtime-final-verification.json`；旧wheel来源与回退证据见 `runtime-before.json`。
- 未启动真实录制、未访问机械臂串口、未提交代码。早期一条隔离不充分的RED测试意外运行camera-only检查，已修复隔离并在implementation-report.md记录。

启动脚本30秒外层timeout覆盖检查进程；CLI的27秒期限覆盖相机采集阶段。几何只看首尾采样帧，光照看全部样本；这不能保证检出采样之外的变化或同均值局部条纹。现有启动检查不替代采集时保持相机/纸张/碗固定。
