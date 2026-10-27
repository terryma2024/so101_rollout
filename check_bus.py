"""只读：持续读取主臂或从臂各舵机位置，统计通信失败，用于排查接触不良（不上扭矩，手臂不会动）。

用法：uv run check_bus.py [leader|follower] [秒数]
运行期间来回活动手腕、夹爪，观察哪个舵机出现失败。
"""

import pathlib
import sys
import time

import scservo_sdk as scs

PRESENT_POSITION = 56

env = dict(l.split("=", 1) for l in pathlib.Path(__file__).with_name("arms.env").read_text().split("\n") if "=" in l and not l.startswith("#"))
arm = sys.argv[1] if len(sys.argv) > 1 else "leader"
duration = float(sys.argv[2]) if len(sys.argv) > 2 else 30
port = env["LEADER_PORT"] if arm == "leader" else env["FOLLOWER_PORT"]

ph = scs.PortHandler(port)
pk = scs.PacketHandler(0)
ph.openPort()
ph.setBaudRate(1_000_000)

ids = range(1, 7)
fails = {i: 0 for i in ids}
total = 0
start = time.time()
print(f"检查 {arm}（{port}），{duration:.0f} 秒，现在开始活动手臂……")
while time.time() - start < duration:
    total += 1
    for i in ids:
        if pk.read2ByteTxRx(ph, i, PRESENT_POSITION)[1] != scs.COMM_SUCCESS:
            fails[i] += 1
            print(f"{time.time() - start:6.1f}s  舵机 {i} 无响应")
ph.closePort()

print(f"\n共读取 {total} 轮：")
for i in ids:
    print(f"  舵机 {i}: 失败 {fails[i]} 次")
