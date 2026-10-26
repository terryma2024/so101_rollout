#!/usr/bin/env bash
set -e; cd "$(dirname "$0")"; source arms.env
uv run lerobot-calibrate --teleop.type=so101_leader --teleop.port="$LEADER_PORT" --teleop.id="$LEADER_ID"
