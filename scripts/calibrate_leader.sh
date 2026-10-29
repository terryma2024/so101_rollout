#!/usr/bin/env bash
set -e
source "$(dirname -- "${BASH_SOURCE[0]}")/lib/common.sh"
so101_init
so101_source_defaults "$SO101_CONFIG_DIR/arms.env"
uv run --no-sync lerobot-calibrate --teleop.type=so101_leader --teleop.port="$LEADER_PORT" --teleop.id="$LEADER_ID"
