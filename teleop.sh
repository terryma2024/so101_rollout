#!/usr/bin/env bash
set -e; cd "$(dirname "$0")"; source arms.env
uv run lerobot-teleoperate \
  --robot.type=so101_follower --robot.port="$FOLLOWER_PORT" --robot.id="$FOLLOWER_ID" \
  --robot.cameras="{ wrist: {type: opencv, index_or_path: $WRIST_CAM, width: 640, height: 480, fps: $WRIST_CAM_FPS} }" \
  --teleop.type=so101_leader --teleop.port="$LEADER_PORT" --teleop.id="$LEADER_ID" \
  --display_data=true
