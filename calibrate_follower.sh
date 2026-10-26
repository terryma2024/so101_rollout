#!/usr/bin/env bash
set -e; cd "$(dirname "$0")"; source arms.env
uv run lerobot-calibrate --robot.type=so101_follower --robot.port="$FOLLOWER_PORT" --robot.id="$FOLLOWER_ID"
