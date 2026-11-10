# Offline evidence tools

Camera color experiments from 2026-11-02 through 2026-11-10 have a
[complete report](../docs/experiments/camera-color-20261110.md) and a
[read-only verification entry point](camera_color_20261110/README.md).
Run `python3 -m tools.camera_color_20261110.verify` to check the archived snapshots
without hardware access; add `--raw-root /data/work/so101-evidence/real-robot`
to verify retained streams and reproduce all saved PNGs.

Run these modules from the repository root with `python -m tools.<module>`.
They support dataset review, explicit human outcome annotations, collection cards,
and evidence assets. They are separate from robot runtime imports and are not
installed in the application wheel. No robot dependencies are added by this toolkit.
The source scripts and their hashes are recorded in [source-provenance.json](source-provenance.json).

## Environment and output locations

Use a separate optional environment rather than modifying the robot environments.
The existing tools environment on this machine is `/data/work/venvs/so101-rollout-tools`.
For a new environment, install [requirements.txt](requirements.txt):

```bash
python3 -m venv "$TOOLS_ENV"
"$TOOLS_ENV/bin/python" -m pip install -r tools/requirements.txt
```

Set `TOOLS_ENV` to your chosen environment first, and run all examples from the
repository root. Here `python` means that environment's Python (activate it or use
its absolute interpreter path). Pillow, NumPy, pandas, PyArrow, PyAV and OpenCV are
the offline dependencies. Collection/evaluation card rendering also needs the
system Noto Sans CJK fonts; collection rendering accepts `--font` and `--bold-font`.
Explicit printing requires the system `lp` command and a configured printer.

Use fresh external output paths. Dataset review and renderers create a new output
directory and reject an existing one; do not reuse an evidence directory. Keep
outputs outside datasets, calibration inputs and the repository. For this migration,
validation artifacts belong under
`/data/work/so101-evidence/real-robot/p0-20261029T215724/tools-migration/`.
Examples use variables such as `DATASET`, `FRESH_EXTERNAL_DIR`, `PLAN`, and
`DATASETS_ROOT`; set them to your own paths before running commands.

## Review a recorded dataset

```bash
python -m tools.review_dataset "$DATASET" --output "$FRESH_EXTERNAL_DIR"
```

The reader supports LeRobot v3 parquet/video data and defaults to `side` and
`wrist` cameras (`--cameras side wrist` is explicit). FPS is inferred from the
dataset's `meta/info.json` `fps` value, rather than assuming 20 or 30 fps. It reads
each camera's episode timestamp interval and chunk/file indices from metadata;
it does not assume all videos are in chunk 000 or file 000.

Outputs include `integrity-light.json`, first/last frames, per-episode contact
sheets and camera overview previews. Checks cover episode membership, lengths,
timestamps, frame indices, finite state/actions when present, and camera frame
counts. A failed integrity check returns a nonzero exit status. Integrity is not
task success: `final_in_bowl` and `first_grasp_success` remain unknown until a
person reviews them. Short records (one frame or less) are retained and flagged;
duration alone never marks an episode as a failed grasp or failed task.

## Summarize human outcome annotations

```bash
python -m tools.summarize_results "$ANNOTATIONS_JSON" --output "$FRESH_EXTERNAL_DIR"
```

The input is a JSON array of annotations, for example:

```json
[
  {
    "color": "green",
    "round": 1,
    "recorded_episode": 1,
    "layout_row": 1,
    "final_in_bowl": true,
    "first_grasp_success": null,
    "excluded": false
  }
]
```

Use one-based actual recorded episode numbers, not plan card IDs. The tuple
`color`, `round`, `recorded_episode` must be unique. Outcome fields accept `true`,
`false`, or `null` (unknown). Mark final stable placement after visually checking
the bowl and first-grasp success separately. Preserve observations about human
assistance, occlusion, retries and layout variants in additional fields. The tool
does not infer labels from motion completion, duration or integrity checks.

It writes `summary.json` with color, round, layout and first-grasp counts, plus
`results.csv` containing the original annotations. Excluded rows remain in the CSV
but do not contribute to summary counts. Unknown final outcomes remain in trial
counts and are also counted as unknown. The checked-in
[P0 annotations](plans/p0-20261029-annotations.json) preserve the reviewed session
labels; do not silently replace unknown first-grasp labels with success.

## Render collection cards

```bash
python -m tools.render_collection "$PLAN" \
  --output "$FRESH_EXTERNAL_DIR" --datasets-root "$DATASETS_ROOT"

# Select any subset by repeating --batch; omit it for all batches.
python -m tools.render_collection tools/plans/p2-20261030.json \
  --output "$ANOTHER_FRESH_EXTERNAL_DIR" --datasets-root "$DATASETS_ROOT" \
  --batch A --batch A2
```

The renderer writes A4 PDFs, full-size PNGs, previews bounded to 1600 px, a render
manifest, and reference recording command text. Rendering does not record or
print. `--batch` accepts plan batch IDs, currently `A`, `A2`, `B`, `B2`.
`--datasets-root` must match the fixed recording root `/data/work/so101-datasets`;
other values are rejected because `record.sh` does not accept a destination
override. The option labels the intended recording folder on cards.

The reviewed [P2 plan](plans/p2-20261030.json) keeps four independent folders:

| Batch | Dataset folder | Planned cards | Episodes |
|---|---|---|---:|
| A | `real-cube-bowl-p2-green-20261030` | G01–G10 | 10 |
| A2 | `real-cube-bowl-p2-green-extra-20261030` | G11–G40 | 30 |
| B | `real-cube-bowl-p2-red-20261030` | R01–R20 | 20 |
| B2 | `real-cube-bowl-p2-red-extra-20261030` | R21–R40 | 20 |

Each folder starts recorded episode numbering at 1. Preserve the exact tasks
`Put the green cube into the paper bowl` and `Put the red cube into the paper bowl`.
See [record-p2-20261030.txt](record-p2-20261030.txt) for the four manual, multiline
recording commands. The old cards have already been printed; do not print them
again as part of migration validation. Keep the first 30 and supplementary 50
plans intact. If all additions are accepted, separate ACT totals become green 133
and red 132. These are conditional training counts, not claims of collected success.

## Plan language coverage

```bash
python -m tools.language_coverage "$PLAN" --output "$FRESH_JSON_FILE"
python -m tools.language_coverage "$PLAN" --output "$ANOTHER_FRESH_JSON_FILE" --cells-only
```

This checks whether planned physical green/red placements occur under both
instructions. The default key includes cells, offsets and angles; `--cells-only`
coarsens the key to cells and can hide geometric differences. The JSON reports
paired conditions and demonstrations with their plan IDs. The output file must
not already exist. This is a planning check, not proof of matched real camera
scenes, balanced accepted data, or actual language selection.

The longer-term goal is one SmolVLA model that selects red or green from the task
instruction. Preserve independent source datasets, exact color labels and their
provenance. Produce a derived multi-task export later, after manual acceptance
and checks for actual scene coverage; keep the separate ACT training workflow.

## Assets and image inspection

```bash
python -m tools.assets size "$IMAGE"
python -m tools.assets preview "$IMAGE" "$FRESH_PREVIEW"
python -m tools.assets manifest "$EVIDENCE_DIR" "$MANIFEST_JSON"
# Only run when explicitly intending to print:
python -m tools.assets print --printer "$PRINTER" "$PDF"
```

Check pixel dimensions before viewing any image. View a preview with a longest
edge no greater than 1600 px by default, retaining the original. Crop a local
region from the original when small text or fine detail needs inspection; avoid
loading multiple full-size originals in succession. The preview helper refuses
to overwrite the original or an existing preview. The manifest records relative
paths, byte sizes and SHA-256 hashes and rejects symlink inputs. Choose a fresh
manifest path; the command rejects an existing output file.

Printing is an explicit action requiring `--printer`; it requests one-sided A4
color output. No review or rendering command submits a print job.

## Position diagnostics and evaluation cards

Run position diagnostics after producing dataset review frames, or render blank
P0 evaluation forms with an explicit run ID:

```bash
python -m tools.cube_positions --review-dir "$REVIEW_DIR" \
  --calibration-dir "$CALIBRATION_DIR" --layout "$LAYOUT_JSON" \
  --output "$FRESH_EXTERNAL_DIR"
python -m tools.render_evaluation --layouts "$LAYOUTS_JSON" \
  --run-id "$RUN_ID" --output "$ANOTHER_FRESH_EXTERNAL_DIR"
```

`cube_positions` reads paired `epN-side-first.jpg` / `epN-side-last.jpg` images from
the review directory. Calibration needs `intrinsics-side.json` (`K`, `D`) and
`extrinsics-side.json` (`position_cm`, `forward`, and frame `image_up` vectors).
The layout JSON needs `cells` mapping cell names to two-dimensional centimeter
coordinates and `bowl` giving its two-dimensional center. A fresh output directory
contains `cubes.json` and bounded first/last previews; a fresh `.json` output path
writes only the estimates. Nearest cell and bowl distance use HSV/component
detection and assume cube centers 1 cm above the table.

Treat these positions as diagnostic estimates, not ground truth or verified robot
coordinates. Calibration must match the original side-frame pixel coordinates;
resized previews cannot substitute for calibration images. Calibration becomes
stale when the camera, paper mat, bowl or reference frame moves; verify alignment
before using estimates. Detection, nearest-cell assignments and bowl distance do
not establish a successful grasp or stable final placement.

`render_evaluation` writes a seven-page PDF (one layout page and six blank record
sheets), bounded previews and `render-manifest.json`. Its P0 protocol is fixed:
ten layouts, green/red each three rounds, ordered green r1, red r1, red r2, green
r2, green r3, red r3. `--run-id` accepts 1–64 letters, digits, hyphens or underscores
and appears in the suggested dataset names. `--font` overrides the CJK font.
[control-layouts.json](plans/control-layouts.json) preserves the session's ten
green/red cell pairs. For red-target evaluation the renderer swaps the physical
cube colors while retaining the original green cell as target; these forms do not
describe identical physical scenes under both instructions. Blank forms are plans,
not recorded evaluation results. Neither command prints, records or drives the robot.

## Training queue

`queue_training.py` is a standalone stdlib script; copy the same file into the
remote training evidence directory alongside the approved `run.sh` and config:

```bash
python3 queue_training.py --detach --evidence "$RED_EVIDENCE" \
  --green-evidence "$GREEN_EVIDENCE" --green-checkpoint "$GREEN_FINAL_CHECKPOINT"
```

The detached queue records `queue.pid`, `queue.log`, and atomic
`queue_status.json`. It checks green every 60 seconds (`waiting_green`) and
requires `exit_code=0` plus nonempty final `config.json` and `model.safetensors`.
Failure, disappearance, or incomplete completion evidence produces `blocked`.
After green succeeds, guarded `run.sh` validates dataset approval, excludes other
trainers, and acquires the RED run lock. Queue status becomes `running_red`, then
`completed` or `blocked` when the run exits. The queue does not operate the robot.

An exclusive persistent `queue_start.json` receipt rejects repeated detached
launches before opening the log or writing the PID; `queue.lock` excludes multiple
active queue processes. `queue_launch.json` prevents automatic retries after a
RED launch, including failures. Existing evidence requires manual inspection;
do not delete receipts to retry without diagnosing the previous run.

## SmolVLA 离线延迟检查

`smolvla_smoke.py` 从已录制的红、绿数据读取双相机观测和六关节状态，运行官方预训练模型的预处理、动作推理和反归一化。它不连接相机或机械臂。数据加载在计时范围外，因此结果是计算预算检查，不含拍摄、串口、限幅、录制或显示开销。

本机独立环境为 `/data/work/venvs/so101-smolvla-061`。2026-10-30 采用 `lerobot==0.6.1`、`torch==2.11.0+cu130`、`transformers==5.5.4`；完整 freeze、安装日志和模型文件 SHA256 位于 `/data/work/so101-evidence/real-robot/smolvla-local-smoke-20261030/setup/`。ACT 环境保持原样。

新环境可用 `uv venv --python 3.12 /data/work/venvs/so101-smolvla-061`，再执行 `uv pip install --python /data/work/venvs/so101-smolvla-061/bin/python -r tools/smolvla-requirements.txt`。该文件固定直接依赖；本次实际环境的完整传递依赖版本以证据中的 `freeze.txt` 为准。

从仓库根目录运行，`--output` 必须是尚不存在的目录：

```bash
HF_HUB_OFFLINE=1 HF_HOME=/data/models/huggingface TORCH_HOME=/data/models/torch \
  /data/work/venvs/so101-smolvla-061/bin/python tools/smolvla_smoke.py \
  --policy /data/models/huggingface/hub/models--lerobot--smolvla_base/snapshots/5e8d12a6e2975b0e5e5fce7c8caf47c371d257b6 \
  --vlm /data/models/huggingface/hub/models--HuggingFaceTB--SmolVLM2-500M-Video-Instruct/snapshots/7b375e1b73b11138ff12fe22c8f2822d8fe03467 \
  --green-dataset /data/work/so101-datasets/real-cube-bowl-green-p2-merged-20261030 \
  --red-dataset /data/work/so101-datasets/real-cube-bowl-red-p2-merged-20261030 \
  --output /data/work/so101-evidence/real-robot/smolvla-local-smoke-20261030/recheck-fp32 \
  --precision float32 --warmup 5 --chunks 50 --tick-chunks 4
```

用 `--precision autocast-bfloat16` 比较 BF16，并换一个输出目录。脚本分别报告完整 chunk、队列边界 tick 和缓存动作 tick 的 p50/p95/p99/max、50 ms 超时比例，以及带节拍的离线同步循环频率；原始逐次数据保存在 `samples.json` 和 `samples.csv`。每种颜色测试前重置动作队列。

本次固定 `camera1=wrist`、`camera2=side`；不提供第三路相机，`empty_cameras=0`，不虚构第三张真图。图像从 640×480 按官方配置补边至 512×512。此映射是本次测量约定，训练与部署需沿用，改变后应重测。完整 base checkpoint 严格加载后提供全部权重，故 `load_vlm_weights=False` 避免再下载并覆盖一份上游 VLM 权重。

base 统计量仅用于验证加载和延迟，不能据此认定该模型已适配本任务。chunk 总耗时小于 2.5 秒，只说明 50 动作块的吞吐预算可能足够；同步边界超过 50 ms 时仍不能保证连续 20 Hz。异步或 RTC 的效果必须另行验证。

## SmolVLA 异步提前推理检查

`smolvla_async.py` 是离线基础异步probe，不是机器人入口，也不是官方RTC运行效果的验证。单个worker独占policy、处理器及CUDA stream，主循环仅消费已转为CPU的动作；剩余10步时发起下一块推理。新块按请求时的目标tick对齐，丢弃已经过去的前缀，并替换尚未执行的未来动作。线程间只允许一个在途请求，包括尚未消费的完成结果。

从仓库根目录使用独立环境运行，模型和数据路径与上面的同步smoke相同：

```bash
HF_HUB_OFFLINE=1 HF_HOME=/data/models/huggingface TORCH_HOME=/data/models/torch \
  /data/work/venvs/so101-smolvla-061/bin/python -m tools.smolvla_async \
  --policy /data/models/huggingface/hub/models--lerobot--smolvla_base/snapshots/5e8d12a6e2975b0e5e5fce7c8caf47c371d257b6 \
  --vlm /data/models/huggingface/hub/models--HuggingFaceTB--SmolVLM2-500M-Video-Instruct/snapshots/7b375e1b73b11138ff12fe22c8f2822d8fe03467 \
  --green-dataset /data/work/so101-datasets/real-cube-bowl-green-p2-merged-20261030 \
  --red-dataset /data/work/so101-datasets/real-cube-bowl-red-p2-merged-20261030 \
  --output /data/work/so101-evidence/real-robot/smolvla-async-20261030/recheck-fp32 \
  --seconds 90 --prefetch 10
```

输出目录须尚不存在。脚本先等待新任务首块填充，单独报告冷启动和切换停顿，再执行90秒green、真实在途切换、10秒red、8秒人工延迟压力场景。固定绝对20Hz时钟，允许5ms的OS唤醒抖动；迟到超过5ms则跳到未来tick并等待，记录skip，不连续补发历史动作。分别报告控制tick频率、实际可用动作频率、断粮、全部成功动作之间的间隔（含跨断粮的长间隔）、CPU执行耗时、队列深度、观测年龄和块衔接数值跳变。压力场景不补造hold动作，其预算失败是预期结果。

切换/reset通过generation清空未来动作，旧任务在途结果返回后必须拒绝；worker内再重置policy。模型仍为未针对本任务微调的base，动作跳变仅是native units诊断，不代表SO101运动平滑或安全。输入为按tick循环的CPU缓存录像，无闭环反馈，也不含真实相机、串口、显示和录制开销。正式数据保存在各run的`report.json`、`events.json/csv`和各phase的`ticks.json/csv`。

## SmolVLA 双任务数据准备

`prepare_smolvla_data.py` 固定了2026-10-30首轮实验的来源和分组；后续迭代需明确更新`SOURCES`，不能不加审查地把新数据递归混入。运行使用独立SmolVLA环境，并指定三个尚不存在的输出目录：

```bash
HF_HUB_OFFLINE=1 HF_HOME=/data/models/huggingface \
  /data/work/venvs/so101-smolvla-061/bin/python -m tools.prepare_smolvla_data \
  --train-root "$FRESH_TRAIN_ROOT" \
  --validation-root "$FRESH_VALIDATION_ROOT" \
  --evidence "$FRESH_EVIDENCE_DIR"
```

来源为已验收green/red各133条。按完整来源录制folder划分：train为green pilot/main61、green P2 10+30、old red clean92、red P2 extra21，共214条63732帧；validation为green adjacent32和red P2 first20，共52条17864帧。不宣称布局或日期独立留出；同一物理布局可能在两个split中出现。跨split完整数值轨迹内容hash必须无重复，排除的原green-extra第3条和old red第11条不得通过清洗索引重映射重新进入。

脚本先与已批准133+133合并集逐条比较数值，再冻结split；使用独立源副本调用官方聚合，修复派生元数据自指针，重算数值统计。验收包括完整视频解码、每条episode两端真实loader读取、精确任务映射、全部数值特征统计、按split图像摘要重聚合、源文件成员和SHA256不变。批准回执和文件SHA manifest写在evidence，数据和视频保存在外部目录。

训练根目录的`meta/stats.json`仅由train episodes拟合。validation保留自身描述统计用于审计，其`meta/normalization-reference.json`指向train统计及SHA256。训练及验证forward必须共用train-fitted预/后处理器；仅记录引用文件不等于已经证明实际模型使用了这些统计，此项由训练smoke验证。两种颜色的validation loss应分别报告，不能用frame比例不平衡的总体均值替代。

## SmolVLA session-split fine-tuning

The full Python 3.12/CUDA 13.0 dependency lock is [locks/smolvla-cu130-py312.txt](locks/smolvla-cu130-py312.txt). Install it only into the independent SmolVLA environment. The tested PyPI torch 2.11.0 wheel reports runtime `2.11.0+cu130`; the project application wheel is intentionally excluded from the training environment.

`prepare_smolvla_training.py` materializes an offline bootstrap from the pinned official base. Model weight bytes remain identical; only camera feature declarations and local VLM/tokenizer paths are adapted. It exports a complete validated training configuration with the pinned library's optimizer and scheduler presets. Use `python -m tools.prepare_smolvla_training --help` for paths and options.

`train_smolvla.py` is the required training entry, invoked as `python -m tools.train_smolvla --config CONFIG --validation-root VALIDATION_ROOT --audit FRESH_AUDIT_DIR`. It temporarily adapts the official LeRobot dataset factory to the already frozen whole-source-session split: train214 episodes/63732 frames and validation52 episodes/17864 frames. It does not apply a second random or tail split. `dataset.eval_split` records the overall 52/266 fraction for the library validation guard; do not pass this configuration directly to raw `lerobot-train`, which would split the training dataset again.

All training and validation forwards share the one train-fitted processor pair. Validation retains its own descriptive `meta/stats.json`, but its `normalization-reference.json` must identify the train statistics file and SHA. The adapter verifies pre-state, pre-action, and post-action mean/std against train statistics. Validation task losses use valid-timestep weighting matching native SmolVLA, including batches that cross a task boundary. Official optimization, dataloaders, checkpointing, and evaluation remain in use; scoped factory/audit replacements are restored after exit.

`verify_smolvla_training.py` strictly reloads a saved checkpoint on CPU, checks all three saved processor statistics, finite loss/gradient audit, and observed red/green language inputs in train and validation. It never initializes CUDA.

The first formal configuration is 20000 steps, batch32, FP32, save/evaluate every5000 steps, all17864 held-out frames (`max_eval_samples=0`), seed1000, default frozen VLM/vision and trainable action expert/state projection. It represents about10.04 frame epochs. The base scheduler preset 1000 warmup/30000 decay steps automatically scales to666 warmup/20000 decay steps in pinned LeRobot0.6.1; actual scaling is logged. The100-step local smoke uses64 validation frames only to check the execution path, not to establish held-out performance.

Copy the reviewed [run_smolvla_training.sh](run_smolvla_training.sh) into the training evidence directory as `run.sh`, alongside frozen `source/tools/`, `config.json`, dependency/model/data manifests, and approvals. It acquires run/GPU locks, calls the CPU-only [guard](guard_smolvla_training.py), rejects any active trainer or changed approved files/versions, records PID/timestamps/real exit code, then runs the adapter and CPU-verifies the final checkpoint. The durable queue managed by the main agent starts it only after RED ACT successfully finishes. Existing run evidence or output is refused; the script does not silently resume or overwrite.

The2026-10-30 bundle is `/data/work/so101-evidence/real-robot/smolvla-finetune-20261030/training/` on both machines. `environment_approved.json`, `model_approved.json`, and `local_smoke_approved.json` are the training-side approval receipts. Formal output is `/data/work/so101-policies/real-smolvla-red-green-v1-20261030`.

## SmolVLA real-robot smoke entry

Run from the checkout with `./rollout_smolvla.sh <fresh-dataset-name> [episodes] [pretrained_model]`.
It uses the separate `/data/work/venvs/so101-smolvla-061` environment and defaults to
`real-smolvla-red-green-v1-20261030/checkpoints/020000/pretrained_model`.
`TASK` accepts the exact green or red training instruction. Both cameras are
explicitly mapped as wrist→camera1 and side→camera2. The script locks camera
settings and requires preflight to pass before connecting the follower.

`DRY_RUN=1` prints arguments without accessing cameras or robot; `CHECK_ONLY=1`
locks and checks cameras, then exits without connecting the robot. This entry
uses the repository's asynchronous `so101_async` backend with official episodic
recording, 50 action steps, 20 Hz target, 30-second episodes and `MAX_REL=30`.
One worker owns policy/processor/CUDA work; the control thread consumes CPU
actions. With 10 remaining steps (500 ms at 20 Hz), it predicts the next chunk
from the current observation while executing the old chunk. Completed chunks
discard elapsed prefixes and replace future commands. This does not enable
RTC prefix guidance or add action smoothing. `TE=1` is rejected.

`PREFETCH_STEPS=10` and `N_ACTION_STEPS=50` are the defaults; prefetch must be
positive and smaller than the action horizon. Pause/reset invalidates the
generation immediately; old in-flight results cannot publish into the next
episode. Model and processors reset on the worker before its first fresh request.
No synthetic hold command is sent on starvation; more than 0.5 seconds of
continuous starvation aborts the policy loop. Startup permits up to 30 seconds
for the first chunk. The preflight evidence directory also receives
`async-telemetry.json` on normal teardown, including monotonic action availability
times, chunk timings, discarded prefixes, skipped ticks, starvation and reset
generations. These action times precede the serial send; dataset timestamps
remain synthetic frame-index/FPS timestamps, and recorded actions retain
official LeRobot's pre-clamp semantics.

To exercise this exact backend without hardware (from the checkout root):

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HOME=/data/models/huggingface \
PYTHONPATH=src:. /data/work/venvs/so101-smolvla-061/bin/python \
  -m tools.smolvla_async_rollout_check \
  --policy /data/work/so101-policies/real-smolvla-red-green-v1-20261030/checkpoints/020000/pretrained_model \
  --green-dataset /data/work/so101-datasets/eval-smolvla-5k-green-smoke-20261031 \
  --red-dataset /data/work/so101-datasets/eval-smolvla-5k-red-smoke-20261031 \
  --ticks-per-color 400 --output "$FRESH_EXTERNAL_DIR"
```

The check replays recorded observations through the actual engine, crosses
multiple chunk boundaries, and forces a reset while real inference is pending.
It excludes camera acquisition, serial sends, visualization and dataset writes;
passing does not establish real-robot 20 Hz or grasp/color-selection success.

For the first paired smoke, keep physical placements green A1/red C3 under both
instructions, restore cubes and empty bowl before each run, and use separate
fresh dataset names per color. Start from the same folded pose. Record correct
color selection and final placement separately. Each task runs in a separate
process. Official episodic recording resets the async generation per episode;
model and processor reset calls run only on the inference worker.

After the failed 5k hardware smoke, the default candidate is 20k: matched-input
offline tests show lower within-chunk action noise. This is candidate selection,
not a verified fix or hardware success claim. Preserve original 5k results; do not
continue unattended robot runs. The 15k checkpoint remains an explicit alternative.
