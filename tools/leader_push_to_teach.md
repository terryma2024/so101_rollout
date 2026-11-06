# Leader gripper-to-teach feasibility probe

This standalone leader-only experiment holds the five arm joints at their current positions and uses movement of the light, torque-free gripper to request teaching. It never opens a follower or runs a policy. The default command only monitors raw registers and leaves all existing torque states unchanged:

```bash
/data/work/venvs/so101-smolvla-061/bin/python tools/probe_leader_push_to_teach.py --duration 30
```

The leader port defaults to `LEADER_PORT` in the environment or `config/arms.env`; `--port` overrides it. The configured follower port and its symlink aliases are refused. Check the printed port belongs to the leader and stop other controllers before testing.

For the active test, support the leader in a comfortable pose, with all six motors' torque initially **off**:

```bash
/data/work/venvs/so101-smolvla-061/bin/python tools/probe_leader_push_to_teach.py \
  --enable-release --trigger-mode gripper-motion --duration 30 \
  --gripper-displacement 30 --sustain-seconds 0.25
```

1. Type `ARM` while supporting the leader. The program writes and verifies the five arm joints' current raw positions as their targets, then enables only those five joints. It never enables gripper torque: leaving the gripper off from the start provides the requested torque-free gripper without briefly energizing it. No different reference pose is commanded; enabling torque can still cause small mechanical corrections.
2. Gradually remove your supporting force, keeping hands nearby. Wait for `Ready` before moving the gripper. The default two-second settling interval accommodates support transfer and passive gripper motion. A rolling 0.5-second gripper-position window must then stay within eight raw ticks. Arm position/load/current variations do not block this gripper baseline. Unstable windows retry for at most twelve seconds after settling.
3. Once `Ready`, support the arm and open or close the light gripper. Absolute displacement **greater than 30 raw ticks** from its fixed median baseline for 0.25 seconds triggers release of the five held axes. A brief spike resets the candidate. The program never automatically rebases while armed. The threshold is an unvalidated starting value; use `--gripper-displacement` to adjust it after reviewing evidence. Direct position subtraction assumes the limited gripper travel does not cross a raw encoder wrap.
4. After all joints' torque-off readbacks are verified, move the supported arm to teach. Raw positions are logged for up to eight seconds (`--teaching-seconds`), bounded by total `--duration`. Torque is never automatically re-enabled.

`--gripper-baseline-seconds`, `--settle-seconds`, `--baseline-timeout-seconds`, `--baseline-position-span` and `--sustain-seconds` control timing and stability. The active duration must exceed settling plus baseline timeout. Telemetry is always checked and logged during settling/baseline; push detection remains inactive until `Ready`.

Evidence defaults to a unique directory under `/data/work/so101-evidence/real-robot/`; `--evidence-dir` selects another new directory. `events.jsonl` records settings including trigger mode, raw feedback, baseline medians, trigger displacement, timing, state changes and cleanup outcomes. A baseline timeout reports measured spans and limits, preserving the offending sample. Existing logs are never overwritten. This trace is not a calibrated LeRobot training episode. Raw current/load values are sign-decoded register counts; no physical force/current units are assumed.

`Ctrl+C`, `SIGTERM`, timeout and exceptions after enabling attempt to disable and verify every motor independently. Support the arm before stopping. Communication failure can prevent verification; `release not verified` means the operator must handle arm/power safely. Process kill, USB loss or power failure cannot guarantee software cleanup. Cancelled arming or failed prechecks make no torque writes. Monitoring remains read-only on exit.

The previous experimental effort detector remains available with `--trigger-mode effort`: it holds all six joints and requires same-joint position deviation plus load/current deviation sustained over time. Its baseline uses a stable three-second rolling window (`--baseline-seconds`), including load/current stability. Use light input only; do not push harder if it fails to trigger.

The implementation uses `FeetechMotorsBus.connect()` with its ping/firmware-read handshake, raw `normalize=False` reads and `disconnect(disable_torque=False)`. It avoids `SOLeader.connect()`, calibration/mode/EEPROM writes and torque convenience methods that also write `Lock`. No hardware operation was performed while developing these changes.

```bash
python3 -m pytest tests/test_leader_push_probe.py -q
/data/work/venvs/so101-smolvla-061/bin/python tools/probe_leader_push_to_teach.py --help
```
