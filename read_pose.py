"""只读：读取主臂和从臂当前关节角度并对比（不上扭矩，手臂不会动）。"""
import json
import os
import pathlib

from so101_test.config import load_arms_env

from lerobot.motors import Motor, MotorCalibration, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus

env = load_arms_env()
base = pathlib.Path(os.environ.get("HF_HOME", "~/.cache/huggingface")).expanduser() / "lerobot/calibration"
arms = {
    "leader": (env["LEADER_PORT"], base / f"teleoperators/so_leader/{env['LEADER_ID']}.json"),
    "follower": (env["FOLLOWER_PORT"], base / f"robots/so_follower/{env['FOLLOWER_ID']}.json"),
}
names = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]

pos = {}
for arm, (port, cal_file) in arms.items():
    cal = {n: MotorCalibration(**v) for n, v in json.loads(cal_file.read_text()).items()}
    motors = {
        n: Motor(i + 1, "sts3215", MotorNormMode.RANGE_0_100 if n == "gripper" else MotorNormMode.DEGREES)
        for i, n in enumerate(names)
    }
    bus = FeetechMotorsBus(port=port, motors=motors, calibration=cal)
    bus.connect()
    pos[arm] = bus.sync_read("Present_Position")
    bus.disconnect(disable_torque=False)

print(f"{'joint':14s} {'leader':>9s} {'follower':>9s} {'diff':>7s}")
for n in names:
    l, f = pos["leader"][n], pos["follower"][n]
    print(f"{n:14s} {l:9.1f} {f:9.1f} {f - l:7.1f}")
