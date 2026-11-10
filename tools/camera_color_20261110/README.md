# 相机色彩实验归档与验证

[完整报告](../../docs/experiments/camera-color-20261110.md) 汇总 2026-11-02 历史诊断及 11-10 的基线、曝光、gamma 粗测/细测。源码与统计按实验阶段归档，保留原文件字节及来源 SHA-256。

## 离线验证入口

从 repo 根目录运行。默认仅需 Python 标准库，无相机、机械臂或模型依赖，不运行归档中的脚本，不查询实时硬件，不写原证据或入库快照：

```bash
python3 -m tools.camera_color_20261110.verify
```

检查：161 个入库来源文件的大小/SHA-256、原实验序列和 15 秒记录窗、已记录的前后/恢复控制快照、有效帧数、ROI 范围、JPEG 排除记录及 YUYV/浅粉专项审计的一致性。输出 JSON 到 stdout；缺失、损坏或不一致时非零退出。`recorded_state_equal` 表示历史快照一致，不表示重新查询了现在的设备。

有原始数据时运行：

```bash
.venv/bin/python -m tools.camera_color_20261110.verify \
  --raw-root /data/work/so101-evidence/real-robot
```

此模式额外需要 NumPy、Pillow、OpenCV；原实验使用 OpenCV 4.13.0，现有项目 `.venv` 可用。它检查 24 个外部原始流/逐帧索引/指标文件（约 5 GB）的 SHA-256、帧索引、主机时间单调性、完整帧范围、MJPEG 零填充、不完整尾字节、条件时间窗与指标数组，并将全部 **3417 张 PNG** 与原始字节重新解码逐像素比较。读取图片像素前先用 Pillow 头部检查 640×480 尺寸。此验证不打开相机。

默认模式不重新解码原始流，也不重新计算色卡指标。raw 模式重新验证 PNG 保存一致性和原指标文件身份，不等于重新估计所有 ROI 汇总或重新审计每帧 JPEG 警告。原始分析、JPEG 警告审计与整数 YUYV 复算脚本保留如下，可在独立回放目录重新运行。

## 文件布局与来源

| 路径 | 内容 |
|---|---|
| `verify.py` | 新的统一只读入口，适配各批已有验证逻辑和数据格式 |
| `originals/historical/` | 12 条旧录像离线分析、固定 patch 复核 |
| `originals/baseline/` | 连续基线采集与固定几何 ROI 分析 |
| `originals/exposure/` | 曝光控制、采集、全帧分析、警告帧排除及 YUYV 复算 |
| `originals/gamma-coarse/` | gamma 粗测各阶段原脚本 |
| `originals/gamma-refine/` | gamma 细测各阶段原脚本、浅粉截断专项复核 |
| `../../docs/experiments/camera-color-20261110/snapshots/` | 原报告、统计、ROI、manifest、控制读回、恢复和审计结果 |
| `source-provenance.json` 的 `external_images` | 10 张外部证据预览的路径与哈希，图片不进 Git |
| `../../docs/experiments/camera-color-20261110/source-provenance.json` | 每个副本的原路径、大小与 SHA-256；外部原始文件指纹 |

共归档 32 个原 Python/shell 文件和 129 个原结果/文本快照，共 161 个文件均未改写；10 张预览仅记录外部路径和哈希，图片不进 Git。`originals` 是历史来源副本：

- `analyze*.py`、`baseline_roi_definitions.py`、`finalize.py`、`audit_jpeg.py`、`followup/audit_yuyv.py`、`followup/pink-highlight-audit.py` 处理本地文件；通常按 `__file__` 定位输入并写结果。
- `run_trial.py`、`stream_capture.py`、`capture.py`、`restore-*.sh` 可采集或写硬件控制；保留用于追溯实验执行，不能当离线验证命令运行。旧曝光控制器本身没有新 gamma 控制器的 `--execute-approved` 门槛。
- 原 `verify_trial.py` 会只读查询硬件，`complete_report.py` 也会查询硬件并写证据。统一入口不调用这些脚本。
- 历史原报告含当时待执行的提案，原始提案 JSON 也可能仍标记当时状态。最终已执行事项、授权与结果以总报告和对应 manifest/events 为准。
- 原 `artifact-sha256.json` 清单保留其历史语义；repo 副本校验使用本次 `source-provenance.json`。

## 在独立目录重跑细测离线分析

以下在 repo 根目录执行。`REPLAY` 用 `mktemp` 创建新外部目录；原始流和索引只通过软链接读取。不要把输出指向入库快照或原证据目录。只复制并运行下列离线脚本：

```bash
SOURCE=/data/work/so101-evidence/real-robot/camera-gamma-refine-20261110
ARCHIVE=docs/experiments/camera-color-20261110/snapshots/gamma-refine
SCRIPTS=tools/camera_color_20261110/originals/gamma-refine
REPLAY=$(mktemp -d /data/work/so101-evidence/camera-color-replay-XXXXXX)

cp "$ARCHIVE/manifest.json" "$REPLAY/"
cp "$SCRIPTS/analyze_trial.py" "$SCRIPTS/baseline_roi_definitions.py" \
  "$SCRIPTS/audit_jpeg.py" "$SCRIPTS/finalize.py" "$REPLAY/"
for camera in wrist side; do
  mkdir "$REPLAY/$camera"
  ln -s "$SOURCE/$camera/stream.bin" "$REPLAY/$camera/stream.bin"
  ln -s "$SOURCE/$camera/frames.jsonl" "$REPLAY/$camera/frames.jsonl"
done

.venv/bin/python "$REPLAY/analyze_trial.py"
.venv/bin/python "$REPLAY/audit_jpeg.py"
.venv/bin/python "$REPLAY/finalize.py"

mkdir "$REPLAY/followup"
cp "$SCRIPTS/followup/audit_yuyv.py" \
  "$SCRIPTS/followup/pink-highlight-audit.py" "$REPLAY/followup/"
cp "$ARCHIVE/followup/reference-roi.json" "$REPLAY/followup/"
.venv/bin/python "$REPLAY/followup/audit_yuyv.py"
.venv/bin/python "$REPLAY/followup/pink-highlight-audit.py"
```

`analyze_trial.py` 计算所有完整帧指标，包含启动/等待期；`audit_jpeg.py` 按逐帧 stderr 检查警告；`finalize.py` 排除审计警告帧后生成最终 `statistics.json` 和对照图。应比较最终 JSON，不能使用排除前 `analysis-output.txt` 的有效帧数。YUYV 复算输出应与快照中的 `followup/yuyv-diagnostics.json` 一致，浅粉专项同理。

曝光、粗测可用相同的“独立目录+原始输入软链接”方法。曝光的 `audit_yuyv.py` 从父目录 `roi.json` 读几何，粗测/细测从 `followup/reference-roi.json` 读；曝光未单独保留 `audit_jpeg.py`，可复用细测的通用逐帧审计脚本。原脚本默认值和固定 ROI 只对应本次数据，不是通用相机标定工具。

如需补依赖，使用现有离线工具环境或独立环境，pip 默认镜像为 `https://pypi.tuna.tsinghua.edu.cn/simple/`，不改机器人运行环境。

本次归档的命令、环境和实际验证结果见[验证回执](../../docs/experiments/camera-color-20261110/archive-validation.json)。
