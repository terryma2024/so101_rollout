# Offline evidence tools

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
