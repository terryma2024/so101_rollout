#!/usr/bin/env bash
# 语音/键盘选择红、绿 ACT 的抓取 agent（真机，人必须在机械臂旁边）。
# 用法：./voice_agent.sh [--asr] [--record <评估数据集名>] [--red-policy <pretrained_model>] [--rest a,b,c,d,e,f] ...
# 离线演练（不碰硬件）：./voice_agent.sh --fake-robot green=<数据集根> --fake-robot red=<数据集根>
# 大模型理解：./voice_agent.sh --llm [--llm-model deepseek-flash] [--llm-timeout 3]（需要环境变量 DEEPSEEK_API_KEY；“停”仍走本地规则，失败退回关键词）
# 视觉验证重试：./voice_agent.sh --verify [--max-attempts 10] [--verify-model deepseek-flash] [--verify-timeout 15]（需要 DEEPSEEK_API_KEY，独立于 --llm；“停/回去/q”取消整条重试链）
# 键盘：红 / 绿 / 停 / 回去 + 回车，q 退出。完整参数见 ./voice_agent.sh --help
# 复位位姿是启动时手臂所在的姿态（和 rollout.sh 一样），启动前先把手臂摆到折叠位。
set -e
source "$(dirname -- "${BASH_SOURCE[0]}")/lib/common.sh"
so101_init
so101_source_defaults "$SO101_CONFIG_DIR/arms.env"

VENV=${VENV:-/data/work/venvs/so101-voice-lerobot-061}
test -x "$VENV/bin/python" || { echo "找不到 $VENV/bin/python" >&2; exit 1; }

fake=0; help=0
for arg in "$@"; do
  [ "$arg" = "--fake-robot" ] && fake=1
  [ "$arg" = "-h" ] || [ "$arg" = "--help" ] && help=1
done
if [ "$fake" = 0 ] && [ "$help" = 0 ]; then
  [ -f "$SO101_CONFIG_DIR/camera.env" ] && "$SO101_ROOT/camera_settings.sh" lock >/dev/null
fi

export HF_HOME=${HF_HOME:-/data/models/huggingface} TORCH_HOME=${TORCH_HOME:-/data/models/torch}
unset PYTHONPATH AMENT_PREFIX_PATH COLCON_PREFIX_PATH
exec "$VENV/bin/python" -m so101_test.voice.voice_agent "$@"
