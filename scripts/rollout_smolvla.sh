#!/usr/bin/env bash
# SmolVLA asynchronous episodic rollout; independent of ACT runtime.
# Usage: TASK="Put the green cube into the paper bowl" ./rollout_smolvla.sh <dataset-name> [episodes] [pretrained_model]
# DRY_RUN=1: print command, no camera/robot. CHECK_ONLY=1: camera preflight only.
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/lib/common.sh"
so101_init
so101_source_defaults "$SO101_CONFIG_DIR/arms.env"
name=${1:?usage: ./rollout_smolvla.sh <dataset-name> [episodes] [pretrained_model]}
episodes=${2:-1}
policy=${3:-/data/work/so101-policies/real-smolvla-red-green-v1-20261030/checkpoints/020000/pretrained_model}
TASK=${TASK:-"Put the green cube into the paper bowl"}
MAX_REL=${MAX_REL:-30}
N_ACTION_STEPS=${N_ACTION_STEPS:-50}
PREFETCH_STEPS=${PREFETCH_STEPS:-10}
VENV=/data/work/venvs/so101-smolvla-061
PREFLIGHT_VENV=/data/work/venvs/so101-real-lerobot-061
ROOT=/data/work/so101-datasets/$name
[[ "$name" =~ ^[a-zA-Z0-9][a-zA-Z0-9_-]*$ ]] || { echo 'Invalid dataset name' >&2; exit 2; }
[[ "$episodes" =~ ^[1-9][0-9]*$ ]] || { echo 'episodes must be positive' >&2; exit 2; }
case "$TASK" in
 'Put the green cube into the paper bowl'|'Put the red cube into the paper bowl') ;;
 *) echo 'TASK must be the exact green or red training instruction' >&2; exit 2;;
esac
[[ "$N_ACTION_STEPS" =~ ^[1-9][0-9]*$ ]] && ((N_ACTION_STEPS<=50)) || { echo 'N_ACTION_STEPS must be 1..50' >&2; exit 2; }
[[ "$PREFETCH_STEPS" =~ ^[1-9][0-9]*$ ]] && ((PREFETCH_STEPS<N_ACTION_STEPS)) || { echo 'PREFETCH_STEPS must be positive and less than N_ACTION_STEPS' >&2; exit 2; }
[[ ${TE:-0} == 0 ]] || { echo 'TE is an ACT option; unsupported here' >&2; exit 2; }
[[ -x "$VENV/bin/lerobot-rollout" ]] || { echo 'SmolVLA environment unavailable' >&2; exit 1; }
for file in config.json model.safetensors policy_preprocessor.json policy_postprocessor.json; do
 [[ -s "$policy/$file" ]] || { echo "Missing checkpoint file: $policy/$file" >&2; exit 1; }
done
"$VENV/bin/python" - "$policy" <<'CHECK'
import json,sys
from pathlib import Path
p=Path(sys.argv[1]);c=json.loads((p/'config.json').read_text())
assert c['type']=='smolvla' and c['chunk_size']==50, 'Expected SmolVLA chunk50 checkpoint'
assert all(c['input_features'][k]['shape']==[3,480,640] for k in ['observation.images.camera1','observation.images.camera2'])
CHECK
if [[ -e "$ROOT" && ${RESUME:-0} != 1 ]]; then
 echo "Dataset already exists: $ROOT; select a fresh name or explicitly RESUME=1" >&2; exit 1
fi
rename_map='{"observation.images.wrist":"observation.images.camera1","observation.images.side":"observation.images.camera2"}'
args=(--strategy.type=episodic --inference.type=so101_async --inference.prefetch="$PREFETCH_STEPS"
 --policy.path="$policy" --device=cuda --policy.n_action_steps="$N_ACTION_STEPS"
 --rename_map="$rename_map"
 --robot.type=so101_follower --robot.port="$FOLLOWER_PORT" --robot.id="$FOLLOWER_ID"
 --robot.max_relative_target="$MAX_REL"
 --robot.cameras="{ wrist: {type: opencv, index_or_path: $WRIST_CAM, width: 640, height: 480, fps: $WRIST_CAM_FPS}, side: {type: opencv, index_or_path: $SIDE_CAM, width: 640, height: 480, fps: $SIDE_CAM_FPS, fourcc: MJPG} }"
 --fps=20 --task="$TASK" --dataset.repo_id="local/rollout_$name" --dataset.root="$ROOT"
 --dataset.single_task="$TASK" --dataset.fps=20 --dataset.episode_time_s=30 --dataset.reset_time_s=20
 --dataset.num_episodes="$episodes" --dataset.push_to_hub=false --play_sounds=false)
[[ ${RESUME:-0} != 1 ]] || args+=(--resume=true)
# Optional diagnostics; no flag keeps the existing hard backend unchanged.
if [[ -n ${INFERENCE_RECORDING_PATH:-} ]]; then
 [[ "$INFERENCE_RECORDING_PATH" == /* ]] || { echo 'Recording path must be absolute' >&2; exit 2; }
 [[ ! -e "$INFERENCE_RECORDING_PATH" ]] || { echo "Recording path already exists: $INFERENCE_RECORDING_PATH" >&2; exit 1; }
 args+=(--inference.recording_path="$INFERENCE_RECORDING_PATH")
fi
export HF_HOME=${HF_HOME:-/data/models/huggingface} TORCH_HOME=${TORCH_HOME:-/data/models/torch}
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export PYTHONPATH="$SO101_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
# Structured config export is read-only: no model, camera or serial open.
if [[ -n ${STRUCTURED_ARGS_PATH:-} ]]; then
 [[ -z ${SSH_CONNECTION:-} ]] || unset DISPLAY
 args+=(--display_data=true)
 if ! xdpyinfo >/dev/null 2>&1; then
  args+=(--display_ip="$RERUN_VIEWER_HOST" --display_port="$RERUN_VIEWER_PORT" --display_compressed_images=true)
 fi
 "$VENV/bin/python" - "$STRUCTURED_ARGS_PATH" "${args[@]}" <<'JSON'
import json,sys
with open(sys.argv[1], 'x') as f: json.dump(sys.argv[2:], f)
JSON
 exit 0
fi
if [[ ${DRY_RUN:-0} == 1 ]]; then
 printf '%q ' "$VENV/bin/python" -m so101_rollout.smolvla.rollout "${args[@]}"; printf '\n'; exit 0
fi
# Lock and check cameras before any serial connection. Failed checks stop the run.
[[ -f "$SO101_CONFIG_DIR/camera.env" ]] || { echo 'Missing camera.env' >&2; exit 1; }
"$SO101_ROOT/camera_settings.sh" lock >/dev/null
mkdir -p /data/work/so101-evidence/real-robot
evidence=$(mktemp -d /data/work/so101-evidence/real-robot/smolvla-rollout-preflight-XXXXXXXX)
echo "检查及异步遥测目录: $evidence"
timeout --signal=TERM --kill-after=2s 30s "$PREFLIGHT_VENV/bin/python" -m so101_rollout.camera.preflight  --config "$SO101_CONFIG_DIR/preflight.json" --evidence-dir "$evidence"
if [[ ${CHECK_ONLY:-0} == 1 ]]; then
 echo 'CHECK_ONLY: cameras checked; robot not connected and no actions sent.'; exit 0
fi
[[ -z ${SSH_CONNECTION:-} ]] || unset DISPLAY
args+=(--display_data=true)
if ! xdpyinfo >/dev/null 2>&1; then
 if ! timeout 3 bash -c "</dev/tcp/$RERUN_VIEWER_HOST/$RERUN_VIEWER_PORT" 2>/dev/null; then
  echo "Rerun viewer unavailable at $RERUN_VIEWER_HOST:$RERUN_VIEWER_PORT" >&2; exit 1
 fi
 args+=(--display_ip="$RERUN_VIEWER_HOST" --display_port="$RERUN_VIEWER_PORT" --display_compressed_images=true)
fi
args+=(--inference.telemetry_path="$evidence/async-telemetry.json")
echo "SmolVLA async: target20Hz, chunk=$N_ACTION_STEPS, prefetch=$PREFETCH_STEPS; episode reset invalidates in-flight results."
exec "$VENV/bin/python" -m so101_rollout.smolvla.rollout "${args[@]}"
