#!/usr/bin/env bash
set -e; cd "$(dirname "$0")"; source arms.env

display_args=(--display_data=true)
if ! xdpyinfo >/dev/null 2>&1; then
  # 没有可用的图形界面（例如 SSH 登录）：启动 rerun 网页查看器，在浏览器中查看
  # 网页从 VIEWER_HOST 打开，需允许该来源跨域访问 gRPC 端口（默认只允许 localhost）
  uv run rerun --serve-web --bind 0.0.0.0 --cors-allow-origin "http://$VIEWER_HOST:9090" >/dev/null 2>&1 &
  rerun_pid=$!
  trap 'kill $rerun_pid 2>/dev/null' EXIT
  sleep 3
  echo "rerun 网页查看器：http://$VIEWER_HOST:9090/?url=rerun%2Bhttp://$VIEWER_HOST:9876/proxy"
  display_args+=(--display_ip=127.0.0.1 --display_port=9876)
fi

uv run lerobot-teleoperate \
  --robot.type=so101_follower --robot.port="$FOLLOWER_PORT" --robot.id="$FOLLOWER_ID" \
  --robot.cameras="{ wrist: {type: opencv, index_or_path: $WRIST_CAM, width: 640, height: 480, fps: $WRIST_CAM_FPS} }" \
  --teleop.type=so101_leader --teleop.port="$LEADER_PORT" --teleop.id="$LEADER_ID" \
  "${display_args[@]}"
