"""lerobot-record 的包装：和 teleop_viz.py 一样，限制发往 rerun 的图像数据量，参数与 lerobot-record 相同。

图像按摄像头帧率（IMAGE_HZ）发给 rerun，其余周期只发关节数据，避免查看器反压卡住录制主循环。
录进数据集的内容不受影响。
"""

import os
import time

from lerobot.scripts import lerobot_record
from lerobot.utils.visualization_utils import log_visualization_data

IMAGE_HZ = float(os.environ.get("WRIST_CAM_FPS", 20))

_last_image_time = 0.0


def throttled_log_visualization_data(*args, observation=None, **kwargs):
    global _last_image_time
    if observation is not None:
        now = time.perf_counter()
        if now - _last_image_time >= 1 / IMAGE_HZ:
            _last_image_time = now
        else:
            observation = {k: v for k, v in observation.items() if getattr(v, "ndim", 0) < 2}
    return log_visualization_data(*args, observation=observation, **kwargs)


lerobot_record.log_visualization_data = throttled_log_visualization_data

# --- 按键防抖与空 episode 保护（2026-10-27：第 6 条一开始就结束、0 帧，保存时崩溃）---
# LeRobot 把多出来的一次"结束"（连按两下、按住自动重复）留到下一个阶段，下一阶段一开始就被跳过。
from lerobot.datasets.lerobot_dataset import LeRobotDataset  # noqa: E402
from lerobot.utils import keyboard_input  # noqa: E402

DEBOUNCE_S = 1.0
_original_apply = keyboard_input.apply_recording_control
_last_right = 0.0


def debounced_apply_recording_control(control, events):
    """忽略 1 秒内重复的"结束本段"（n / →）。"""
    global _last_right
    if control == "right":
        now = time.monotonic()
        if now - _last_right < DEBOUNCE_S:
            print("（1 秒内重复的按键已忽略）")
            return
        _last_right = now
    _original_apply(control, events)


keyboard_input.apply_recording_control = debounced_apply_recording_control

_original_record_loop = lerobot_record.record_loop

# --- 侧面相机位置自动校验（2026-10-28：采集时可能碰到侧面相机）---
# 开始录制前和每保存 SIDE_CHECK_EVERY 条（默认 10）后，取一帧侧面画面，用 align_side.py 的方法和参考图比较。
# 两层检查（2026-10-28 用户要求放宽绝对容差）：
#   和训练参考图比：平移 < SIDE_TOL_PX（默认 6 px）、旋转 < SIDE_TOL_DEG（默认 2.5°）；
#   和本次开录时的画面比（录制中被碰到）：平移 < SIDE_DRIFT_PX（默认 3 px）、旋转 < SIDE_DRIFT_DEG（默认 0.8°）。
# 任一超出就响铃、打印调整提示，并在刚保存的这一条之后停止录制（已录的都保存）。
# 调好相机（python align_side.py）后用 RESUME=1 继续。每次结果记到 SIDE_CHECK_LOG。
import datetime  # noqa: E402
import json  # noqa: E402
import pathlib  # noqa: E402

import cv2  # noqa: E402

from ..camera import align_side  # noqa: E402

SIDE_CHECK_EVERY = int(os.environ.get("SIDE_CHECK_EVERY", 10))
SIDE_CHECK_LOG = pathlib.Path(os.environ.get(
    "SIDE_CHECK_LOG", f"/data/work/so101-evidence/real-robot/side-checks/{datetime.date.today():%Y%m%d}.jsonl"))
SIDE_TOL_PX = float(os.environ.get("SIDE_TOL_PX", align_side.TOL_PX))
SIDE_TOL_DEG = float(os.environ.get("SIDE_TOL_DEG", align_side.TOL_DEG))
SIDE_DRIFT_PX = float(os.environ.get("SIDE_DRIFT_PX", align_side.DRIFT_PX))
SIDE_DRIFT_DEG = float(os.environ.get("SIDE_DRIFT_DEG", align_side.DRIFT_DEG))
_session = {"robot": None, "events": None, "started": False, "saved": 0, "ref": None, "baseline": None}


def side_camera_check(when):
    robot = _session["robot"]
    cams = getattr(robot, "cameras", None) or {}
    if "side" not in cams:
        return
    if _session["ref"] is None:
        _session["ref"] = align_side.features(cv2.imread(align_side.DEFAULT_REF))
    imgs = []
    try:
        for _ in range(7):  # median of 7 frames: one frame jitters by a few tenths of a degree
            imgs.append(cv2.cvtColor(cams["side"].async_read(), cv2.COLOR_RGB2BGR))
            time.sleep(0.06)
    except Exception as error:  # noqa: BLE001 - a failed check must not break the recording
        print(f"侧面相机校验没有做成（读不到画面：{error}）")
        return
    img = imgs[-1]
    r = align_side.estimate_median(*_session["ref"], imgs)
    abs_ok = align_side.within(r, SIDE_TOL_PX, SIDE_TOL_DEG)
    drift = None
    base = _session["baseline"]
    if r is not None and base is not None:
        drift = (r[0] - base[0], r[1] - base[1], r[2] - base[2], r[3], r[4])
    drift_ok = drift is None or align_side.within(drift, SIDE_DRIFT_PX, SIDE_DRIFT_DEG)
    ok = abs_ok and drift_ok
    if ok and base is None:
        _session["baseline"] = r  # first passing check of this run: later checks compare against it
    stamp = datetime.datetime.now().strftime("%H%M%S")
    SIDE_CHECK_LOG.parent.mkdir(parents=True, exist_ok=True)
    shot = SIDE_CHECK_LOG.parent / f"side-{datetime.date.today():%Y%m%d}-{stamp}.jpg"
    cv2.imwrite(str(shot), img)
    with SIDE_CHECK_LOG.open("a") as f:
        f.write(json.dumps(dict(time=datetime.datetime.now().isoformat(timespec="seconds"), when=when,
                                ok=ok, abs_ok=abs_ok, drift_ok=drift_ok, result=r, baseline=base, drift=drift,
                                tol=[SIDE_TOL_PX, SIDE_TOL_DEG, SIDE_DRIFT_PX, SIDE_DRIFT_DEG],
                                image=str(shot))) + "\n")
    drift_text = "" if drift is None else f"；相对开录时 平移 ({drift[0]:+.1f}, {drift[1]:+.1f}) px 旋转 {drift[2]:+.2f}°"
    if ok:
        print(f"侧面相机校验（{when}）：{align_side.report(r, SIDE_TOL_PX, SIDE_TOL_DEG)}{drift_text}")
        return
    print("\a" + "!" * 70)
    if not abs_ok:
        print(f"侧面相机位置偏了（{when}）：{align_side.report(r, SIDE_TOL_PX, SIDE_TOL_DEG)}")
    else:
        print(f"侧面相机在录制中被移动了（{when}）{drift_text}"
              f"（允许 {SIDE_DRIFT_PX:g} px / {SIDE_DRIFT_DEG:g}°）")
    print("录制会在这一条之后停止（已录的都已保存）。调整方法：python align_side.py 看实时偏差，调到“已对准”，")
    print("然后用 RESUME=1 加原来的命令继续录剩下的条数。")
    print("!" * 70 + "\a", flush=True)
    events = _session["events"]
    if events is not None:
        events["stop_recording"] = True
        events["exit_early"] = True


# --- 慢循环警告定位（2026-10-28：录制中偶尔出现 "Record loop is running slower (6-8 Hz)"）---
# LeRobot 单次循环超过 1/fps 就打印这条警告。这里把每次警告的时间、阶段（录制/复位）和当时这一条已录的帧数
# 记到 SIDE_CHECK_LOG 旁边的 slow-loop-<日期>.jsonl，录完后可以对到数据集里的具体帧。
import logging  # noqa: E402

SLOW_LOOP_LOG = SIDE_CHECK_LOG.parent / f"slow-loop-{datetime.date.today():%Y%m%d}.jsonl"


class SlowLoopRecorder(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        if "Record loop is running slower" in msg:
            dataset = _session.get("dataset")
            buf = getattr(getattr(dataset, "writer", None), "episode_buffer", None) if dataset is not None else None
            try:
                with SLOW_LOOP_LOG.open("a") as f:
                    f.write(json.dumps(dict(
                        time=datetime.datetime.now().isoformat(timespec="milliseconds"), message=msg[:60],
                        phase=_session.get("phase"), episodes_saved=getattr(getattr(dataset, "meta", None),
                                                                            "total_episodes", None),
                        frame_in_episode=buf["size"] if buf else None)) + "\n")
            except OSError:
                pass
        return True


logging.getLogger().addFilter(SlowLoopRecorder())


def record_loop_fresh(*args, events=None, **kwargs):
    """每个阶段开始时清掉上一阶段残留的"结束"标志，避免新的一条刚开始就结束。"""
    _session["phase"] = "record" if kwargs.get("dataset") is not None else "reset"
    if kwargs.get("dataset") is not None:
        _session["dataset"] = kwargs["dataset"]
    if events is not None and events.get("exit_early") and not events.get("rerecord_episode") \
            and not events.get("stop_recording"):
        print("（清除了上一阶段残留的结束按键）")
        events["exit_early"] = False
    _session["robot"] = kwargs.get("robot", args[0] if args else None)
    _session["events"] = events
    if not _session["started"]:
        _session["started"] = True
        side_camera_check("开始录制前")
    return _original_record_loop(*args, events=events, **kwargs)


lerobot_record.record_loop = record_loop_fresh

_original_save_episode = LeRobotDataset.save_episode


def save_episode_nonempty(self, *args, **kwargs):
    """0 帧的一条不保存（LeRobot 原本会抛 ValueError 让整个录制崩溃）。"""
    if not args and kwargs.get("episode_data") is None and not self.has_pending_frames():
        print("警告：这一条没有录到任何帧，已跳过（不保存）。数据集条数会比计划少 1 条，可用 RESUME=1 补录。")
        return None
    out = _original_save_episode(self, *args, **kwargs)
    _session["saved"] += 1
    total = self.meta.total_episodes
    if SIDE_CHECK_EVERY > 0 and total % SIDE_CHECK_EVERY == 0:
        side_camera_check(f"已保存 {total} 条")
    return out


LeRobotDataset.save_episode = save_episode_nonempty

def main() -> None:
    lerobot_record.main()


if __name__ == "__main__":
    main()
