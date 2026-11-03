#!/usr/bin/env bash
# Manifest session; dry-run unless --execute is explicitly supplied.
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/lib/common.sh"
so101_init
export PYTHONPATH="$SO101_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export HF_HOME=${HF_HOME:-/data/models/huggingface} TORCH_HOME=${TORCH_HOME:-/data/models/torch}
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
exec /data/work/venvs/so101-smolvla-061/bin/python -m so101_rollout.smolvla.persistent_session "$@"
