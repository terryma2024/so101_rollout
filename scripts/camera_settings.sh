#!/usr/bin/env bash
# 锁定 / 恢复两路摄像头的曝光和白平衡，让录制和评估时画面亮度、颜色保持一致。
#   ./camera_settings.sh show   查看当前值
#   ./camera_settings.sh lock   按 camera.env 设为手动曝光 + 固定白平衡（录制、评估前运行）
#   ./camera_settings.sh auto   恢复自动曝光和自动白平衡
#   ./camera_settings.sh snap   两路各截一帧到证据目录，用来判断参数是否合适
# 拔插 USB 或重启后设置会丢失，需要重新 lock。
set -e
source "$(dirname -- "${BASH_SOURCE[0]}")/lib/common.sh"
so101_init
so101_source_defaults "$SO101_CONFIG_DIR/arms.env"
so101_source_defaults "$SO101_CONFIG_DIR/camera.env"

has() { v4l2-ctl -d "$1" -l 2>/dev/null | grep -q "^ *$2 "; }
setc() { if has "$1" "$2"; then v4l2-ctl -d "$1" -c "$2=$3"; else echo "  $(basename "$1"): 没有控制项 $2，跳过" >&2; fi; }

lock_one() {  # device exposure wb [saturation]
  local dev=$1
  [ -e "$dev" ] || { echo "找不到 $dev" >&2; return 1; }
  [ -n "$4" ] && setc "$dev" saturation "$4"
  setc "$dev" power_line_frequency "$POWER_LINE"
  setc "$dev" auto_exposure 1                 # 1 = Manual Mode
  setc "$dev" exposure_time_absolute "$2"
  if [ "$3" = auto ]; then
    setc "$dev" white_balance_automatic 1     # 白平衡保持自动，只锁曝光
  else
    setc "$dev" white_balance_automatic 0
    setc "$dev" white_balance_temperature "$3"
  fi
}
auto_one() {
  local dev=$1
  [ -e "$dev" ] || { echo "找不到 $dev" >&2; return 1; }
  setc "$dev" auto_exposure 3                 # 3 = Aperture Priority Mode（默认）
  setc "$dev" white_balance_automatic 1
}
show_one() {
  echo "== $1 ($2)"
  v4l2-ctl -d "$2" -l 2>/dev/null | grep -E "auto_exposure|exposure_time_absolute|white_balance|power_line|saturation" || echo "  打不开（未连接或被占用）"
}

case "${1:-show}" in
  show) show_one wrist "$WRIST_CAM"; show_one side "$SIDE_CAM" ;;
  lock) lock_one "$WRIST_CAM" "$WRIST_EXPOSURE" "$WRIST_WB" "${WRIST_SATURATION:-}"; lock_one "$SIDE_CAM" "$SIDE_EXPOSURE" "$SIDE_WB" "${SIDE_SATURATION:-}"
        show_one wrist "$WRIST_CAM"; show_one side "$SIDE_CAM" ;;
  auto) auto_one "$WRIST_CAM"; auto_one "$SIDE_CAM"; show_one wrist "$WRIST_CAM"; show_one side "$SIDE_CAM" ;;
  snap) /data/work/venvs/so101-real-lerobot-061/bin/python -m so101_test.camera.calib_capture snap ;;
  *) echo "用法：$0 show|lock|auto|snap" >&2; exit 2 ;;
esac
