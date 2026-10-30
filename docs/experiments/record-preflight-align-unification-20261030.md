# 2026-10-30：自动检查与 align_side 位置标准统一

旧自动检查使用今日快照的背景/纸张独立SIFT、角点5px/旋转1°/缩放2%规则，与原align_side不一致，导致已对准场景被拒绝。最新失败的g7QyMYXO/side-39.png已保存为仓库回归fixture，来源与SHA256见tests/fixtures/preflight/provenance.json。

自动检查现延迟导入并直接调用camera.align_side的features、estimate_median、within和report，训练基准原始字节保存到config/preflight/side-training-reference.png。最近7帧的中心平移严格小于6px、旋转严格小于2.5°；保留中值内点至少10个的质量门槛，失配和非有限结果拒绝通过，不另设缩放门槛。背景及纸张独立几何检查已移除。

光照继续对比今日人工批准的原基准及原阈值，两张基准分别记录来源和SHA256并在相机打开前校验。捕获、释放、超时、失败默认N与人工y/Y继续、原录制路径保持原流程。终端报告实际测量和阈值，result.json分别记录位置和光照来源，对照图标明训练基准与当前画面。

修复及验证证据：/data/work/so101-evidence/real-robot/preflight-align-unification-20261030/。本次实现不访问相机或串口，不启动录制、不提交代码；后续运行环境安装和camera-only复核由主代理记录。

最终验证：root全套314 passed in 2.91s（8 workers，NVMe临时目录，完整JUnit与日志位于 `/data/work/so101-evidence/real-robot/preflight-align-unification-20261030/full-tests-qwzc1m2h`）。实际real环境只重装项目wheel，无依赖升级；源文件、wheel与安装模块字节一致，见 `/data/work/so101-evidence/real-robot/preflight-align-unification-20261030/runtime-verification.json`。实际camera-only检查通过：`/data/work/so101-evidence/real-robot/record-preflight-x6hytmcz/result.json`，中心平移(+0.6,-0.9)px、旋转-0.91°、内点26，两路光照通过。未启动真实record或操作串口。
