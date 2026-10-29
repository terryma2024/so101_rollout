#!/usr/bin/env bash
# 遥操作录制 LeRobot 数据集（方块放进纸碗）。用法：./record.sh <数据集名> [条数]
# 例：./record.sh real-cube-bowl-pilot-20261027 10
# 任务文本默认是抓绿方块；抓红方块：TASK="Put the red cube into the paper bowl" ./record.sh real-cube-bowl-red-20261028 92
# 键盘：n 或 → 结束当前这一段（录制中=本条结束；复位中=立刻开始下一条），r 或 ← 重录本条，q 或 Esc 结束录制并保存。
set -e
source "$(dirname -- "${BASH_SOURCE[0]}")/lib/common.sh"
so101_init
so101_source_defaults "$SO101_CONFIG_DIR/arms.env"

name=${1:?usage: ./record.sh <dataset-name> [num-episodes]}
episodes=${2:-10}
VENV=/data/work/venvs/so101-real-lerobot-061
ROOT=/data/work/so101-datasets/$name
if [ -e "$ROOT" ] && [ "${RESUME:-0}" != 1 ]; then
  echo "$ROOT 已存在；续录请用 RESUME=1 ./record.sh $name $episodes" >&2; exit 1
fi

# 从 SSH 运行时去掉 DISPLAY：否则 LeRobot 会监听本机桌面（X :1）的键盘，SSH 终端里的按键收不到。
# 去掉后它读当前终端的按键（n=下一条，r=重录，q=结束；方向键也可以，但 SSH 下字母更可靠）。
[ -n "${SSH_CONNECTION:-}" ] && unset DISPLAY
display_args=(--display_data=true)
if ! xdpyinfo >/dev/null 2>&1; then
  if ! timeout 3 bash -c "</dev/tcp/$RERUN_VIEWER_HOST/$RERUN_VIEWER_PORT" 2>/dev/null; then
    echo "连不上 $RERUN_VIEWER_HOST:$RERUN_VIEWER_PORT 上的 rerun 查看器，请先在该电脑上运行 rerun" >&2
    exit 1
  fi
  display_args+=(--display_ip="$RERUN_VIEWER_HOST" --display_port="$RERUN_VIEWER_PORT")
fi
# 录制前锁定曝光和白平衡（camera.env），保证每次录制画面一致
[ -f "$SO101_CONFIG_DIR/camera.env" ] && "$SO101_ROOT/camera_settings.sh" lock >/dev/null
resume_args=()
[ "${RESUME:-0}" = 1 ] && resume_args=(--resume=true)

HF_HOME=${HF_HOME:-/data/models/huggingface} WRIST_CAM_FPS=$WRIST_CAM_FPS "$VENV/bin/python" -m so101_rollout.operations.record_viz \
  --robot.type=so101_follower --robot.port="$FOLLOWER_PORT" --robot.id="$FOLLOWER_ID" \
  --robot.cameras="{ wrist: {type: opencv, index_or_path: $WRIST_CAM, width: 640, height: 480, fps: $WRIST_CAM_FPS}, side: {type: opencv, index_or_path: $SIDE_CAM, width: 640, height: 480, fps: $SIDE_CAM_FPS, fourcc: MJPG} }" \
  --teleop.type=so101_leader --teleop.port="$LEADER_PORT" --teleop.id="$LEADER_ID" \
  --dataset.repo_id="local/$name" --dataset.root="$ROOT" \
  --dataset.single_task="${TASK:-Put the green cube into the paper bowl}" \
  --dataset.fps=20 --dataset.episode_time_s=30 --dataset.reset_time_s=20 \
  --dataset.num_episodes="$episodes" --dataset.push_to_hub=false --play_sounds=false \
  "${resume_args[@]}" "${display_args[@]}"
