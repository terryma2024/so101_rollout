#!/usr/bin/env bash
# Copy this reviewed file to the evidence directory as run.sh; queue passes no args.
set -Eeuo pipefail
E=${1:-/data/work/so101-evidence/real-robot/smolvla-finetune-20261030/training}
V=/data/work/venvs/so101-smolvla-061
exec 9>"$E/run.lock"
flock -n 9 || { echo 'Duplicate SmolVLA run refused' >&2; exit 73; }
[[ ! -e "$E/started.txt" ]] || { echo 'Prior run evidence exists' >&2; exit 73; }
exec 10>/data/work/so101-policies/.gpu0-training.lock
flock -n 10 || { echo 'Another GPU training launcher holds the lock' >&2; exit 73; }
cd "$E/source"
export HF_HOME=/data/models/huggingface TORCH_HOME=/data/models/torch
export HF_HUB_OFFLINE=1 PYTHONUNBUFFERED=1
"$V/bin/python" -m tools.guard_smolvla_training --evidence "$E"
finish() {
    local rc=$?
    trap - EXIT
    printf 'exit_code=%s\n' "$rc" > "$E/exit_code.txt"
    date -u +%FT%TZ > "$E/finished.txt"
    exit "$rc"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
printf '%s\n' "$$" > "$E/run.pid"
date -u +%FT%TZ > "$E/started.txt"
"$V/bin/python" -m tools.train_smolvla --config "$E/config.json" \
    --validation-root /data/work/so101-datasets/real-cube-bowl-smolvla-validation-20261030 \
    --audit "$E/runtime-audit" 2>&1 | tee -a "$E/train.log"
"$V/bin/python" -m tools.verify_smolvla_training \
    --checkpoint /data/work/so101-policies/real-smolvla-red-green-v1-20261030/checkpoints/020000/pretrained_model \
    --train /data/work/so101-datasets/real-cube-bowl-smolvla-train-20261030 \
    --audit "$E/runtime-audit" --receipt "$E/final-model-verified.json" --steps 20000 \
    2>&1 | tee "$E/final-verification.log"
