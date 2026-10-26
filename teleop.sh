#!/usr/bin/env bash
set -e; cd "$(dirname "$0")"; source arms.env

display_args=(--display_data=true)
if ! xdpyinfo >/dev/null 2>&1; then
  # 没有可用的图形界面（例如 SSH 登录）：发送到远程电脑上已打开的原生 rerun 查看器
  if ! timeout 3 bash -c "</dev/tcp/$RERUN_VIEWER_HOST/$RERUN_VIEWER_PORT" 2>/dev/null; then
    echo "连不上 $RERUN_VIEWER_HOST:$RERUN_VIEWER_PORT 上的 rerun 查看器，请先在该电脑上运行 rerun" >&2
    exit 1
  fi
  display_args+=(--display_ip="$RERUN_VIEWER_HOST" --display_port="$RERUN_VIEWER_PORT")
fi

uv run lerobot-teleoperate \
  --robot.type=so101_follower --robot.port="$FOLLOWER_PORT" --robot.id="$FOLLOWER_ID" \
  --robot.cameras="{ wrist: {type: opencv, index_or_path: $WRIST_CAM, width: 640, height: 480, fps: $WRIST_CAM_FPS} }" \
  --teleop.type=so101_leader --teleop.port="$LEADER_PORT" --teleop.id="$LEADER_ID" \
  "${display_args[@]}"
