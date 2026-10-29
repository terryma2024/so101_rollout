#!/usr/bin/env bash
set -e
source "$(dirname -- "${BASH_SOURCE[0]}")/lib/common.sh"
so101_init
so101_source_defaults "$SO101_CONFIG_DIR/arms.env"
uv run --no-sync lerobot-calibrate --robot.type=so101_follower --robot.port="$FOLLOWER_PORT" --robot.id="$FOLLOWER_ID"
