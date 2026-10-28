#!/usr/bin/env bash
# 真机 rollout：训练好的策略控制从臂（不接主臂），每条录成评估数据集。
# 用法：./rollout.sh <策略目录 pretrained_model> <评估数据集名> [条数]
# 例：./rollout.sh /data/work/so101-policies/real-act-001-20261027T1007Z/checkpoints/100000/pretrained_model eval-real-act-001-night1 3
# 每条开始前摆好方块；键盘：n 或 → 结束当前这一段（策略运行中=本条结束；复位中=立刻开始下一条），
# r 或 ← 作废并重录本条，q 或 Esc 结束并保存。复位阶段机械臂自动回到启动时的姿态（折叠位）。
# 安全：每一步关节目标离当前位置最多 MAX_REL 度（默认 30，训练数据里遥操作的 p99 约 27 度）。
set -e; cd "$(dirname "$0")"; source arms.env

policy=${1:?usage: ./rollout.sh <pretrained_model dir> <eval-dataset-name> [num-episodes]}
name=${2:?usage: ./rollout.sh <pretrained_model dir> <eval-dataset-name> [num-episodes]}
episodes=${3:-3}
MAX_REL=${MAX_REL:-30}
VENV=/data/work/venvs/so101-real-lerobot-061
ROOT=/data/work/so101-datasets/$name
test -f "$policy/model.safetensors" || { echo "找不到 $policy/model.safetensors" >&2; exit 1; }
if [ -e "$ROOT" ] && [ "${RESUME:-0}" != 1 ]; then
  echo "$ROOT 已存在；续录请用 RESUME=1 ./rollout.sh $policy $name $episodes" >&2; exit 1
fi

[ -n "${SSH_CONNECTION:-}" ] && unset DISPLAY
display_args=(--display_data=true)
if ! xdpyinfo >/dev/null 2>&1; then
  if ! timeout 3 bash -c "</dev/tcp/$RERUN_VIEWER_HOST/$RERUN_VIEWER_PORT" 2>/dev/null; then
    echo "连不上 $RERUN_VIEWER_HOST:$RERUN_VIEWER_PORT 上的 rerun 查看器，请先在该电脑上运行 rerun" >&2
    exit 1
  fi
  display_args+=(--display_ip="$RERUN_VIEWER_HOST" --display_port="$RERUN_VIEWER_PORT" --display_compressed_images=true)
fi
[ -f camera.env ] && ./camera_settings.sh lock >/dev/null
resume_args=()
[ "${RESUME:-0}" = 1 ] && resume_args=(--resume=true)

HF_HOME=${HF_HOME:-/data/models/huggingface} TORCH_HOME=${TORCH_HOME:-/data/models/torch} "$VENV/bin/lerobot-rollout" \
  --strategy.type=episodic \
  --policy.path="$policy" --device=cuda \
  --robot.type=so101_follower --robot.port="$FOLLOWER_PORT" --robot.id="$FOLLOWER_ID" \
  --robot.max_relative_target="$MAX_REL" \
  --robot.cameras="{ wrist: {type: opencv, index_or_path: $WRIST_CAM, width: 640, height: 480, fps: $WRIST_CAM_FPS}, side: {type: opencv, index_or_path: $SIDE_CAM, width: 640, height: 480, fps: $SIDE_CAM_FPS, fourcc: MJPG} }" \
  --fps=20 --task="Put the green cube into the paper bowl" \
  --dataset.repo_id="local/rollout_$name" --dataset.root="$ROOT" \
  --dataset.single_task="Put the green cube into the paper bowl" \
  --dataset.fps=20 --dataset.episode_time_s=30 --dataset.reset_time_s=20 \
  --dataset.num_episodes="$episodes" --dataset.push_to_hub=false --play_sounds=false \
  "${resume_args[@]}" "${display_args[@]}"
