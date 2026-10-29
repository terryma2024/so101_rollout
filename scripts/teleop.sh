#!/usr/bin/env bash
set -e
source "$(dirname -- "${BASH_SOURCE[0]}")/lib/common.sh"
so101_init
so101_source_defaults "$SO101_CONFIG_DIR/arms.env"

display_args=(--display_data=true)
if [ -n "$SSH_CONNECTION" ] || ! xdpyinfo >/dev/null 2>&1; then
  # SSH 登录（即使本机桌面已登录、DISPLAY 可用）或没有图形界面：发送到远程电脑上已打开的原生 rerun 查看器
  if ! timeout 3 bash -c "</dev/tcp/$RERUN_VIEWER_HOST/$RERUN_VIEWER_PORT" 2>/dev/null; then
    echo "连不上 $RERUN_VIEWER_HOST:$RERUN_VIEWER_PORT 上的 rerun 查看器，请先在该电脑上运行 rerun" >&2
    exit 1
  fi
  display_args+=(--display_ip="$RERUN_VIEWER_HOST" --display_port="$RERUN_VIEWER_PORT")
fi

WRIST_CAM_FPS=$WRIST_CAM_FPS uv run --no-sync python -m so101_test.operations.teleop_viz \
  --robot.type=so101_follower --robot.port="$FOLLOWER_PORT" --robot.id="$FOLLOWER_ID" \
  --robot.cameras="{ wrist: {type: opencv, index_or_path: $WRIST_CAM, width: 640, height: 480, fps: $WRIST_CAM_FPS}, side: {type: opencv, index_or_path: $SIDE_CAM, width: 640, height: 480, fps: $SIDE_CAM_FPS, fourcc: MJPG} }" \
  --teleop.type=so101_leader --teleop.port="$LEADER_PORT" --teleop.id="$LEADER_ID" \
  "${display_args[@]}"
