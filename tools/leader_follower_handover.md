# Experimental leader/follower handover

This standalone probe tests the requested manual-pose → follower hold → leader alignment → gripper-triggered teaching sequence. It does not run a policy, record a training dataset, or modify production DAgger code. The probe has been tried on hardware. The new normal-completion Enter-to-release change was verified offline only.

Run from the repository root in a local interactive terminal:

```bash
HF_HOME=/data/models/huggingface /data/work/venvs/so101-smolvla-061/bin/python tools/probe_leader_follower_handover.py --help
HF_HOME=/data/models/huggingface /data/work/venvs/so101-smolvla-061/bin/python tools/probe_leader_follower_handover.py
```

The approved bounded approximate-alignment trial uses this explicit command (no elbow goal compensation):

```bash
HF_HOME=/data/models/huggingface /data/work/venvs/so101-smolvla-061/bin/python tools/probe_leader_follower_handover.py --approximate-alignment
```

This new mode has been verified offline only; no hardware run was performed for this change. Without the option, strict alignment keeps the existing uniform tolerance and dwell. `--approximate-alignment` and `--elbow-compensation` are mutually exclusive.

Ports and distinct arm IDs default to `config/arms.env`, with environment overrides. Existing calibration files default to `$HF_HOME/lerobot/calibration/teleoperators/so_leader/$LEADER_ID.json` and `$HF_HOME/lerobot/calibration/robots/so_follower/$FOLLOWER_ID.json`; when `HF_HOME` is unset, `~/.cache/huggingface` is used. You can explicitly supply `--leader-calibration`, `--follower-calibration`, `--leader-port`, `--follower-port`, `--leader-id`, and `--follower-id`. Calibration must already exist and match read-only motor EEPROM calibration. The program never calibrates automatically or writes EEPROM, operating mode, offsets, limits, or lock registers.

1. Support both arms before starting, with all motor torque already OFF. Clear the leader's entire path and the follower's workspace. A pre-existing torque-on state aborts with **no writes**, so this case leaves that pre-existing state untouched.
2. With both arms free, manually place the follower in the desired starting pose, including gripper opening. Keep supporting it. Type `ARM` and Enter. This captures the follower's current pose, writes those same raw targets, and enables all six follower motors. The leader remains free. Check holding is secure before gradually removing support.
3. Clear the leader's path, keep support close, and type `GO` and Enter. The five leader arm axes first hold their own current pose and then move slowly toward the follower's calibrated arm pose. The leader gripper remains torque OFF throughout. The follower stays held throughout alignment.
4. Wait for `READY`. Strict mode requires measured leader convergence within 0.75 degrees for 0.5 seconds, then captures a stable free-gripper baseline. The explicit approximate mode uses the fixed per-axis bounds and full five-axis stable window described below. Do not move the gripper during this baseline. At `READY`, support the leader without lifting or pushing its arm, then open or close its free gripper by more than 30 raw ticks, sustained for at least 0.25 seconds. These defaults reuse the local leader-only experiment's detector; they are adjustable with `--gripper-displacement` and `--sustain-seconds`.
5. When the trigger is verified, the five leader arm axes release torque with readback. The follower remains powered and follows subsequent leader movement. Move the leader gently. Default teaching time is eight seconds (`--teaching-seconds`). At this deadline, following stops and the follower holds its last commanded target. The leader remains torque OFF; it is never automatically re-enabled. A prominent prompt asks you to support both arms, then press **Enter** to release and exit. This final confirmation wait has no automatic-release timeout. Moving the leader during this wait does not move the follower.
6. While waiting for the final Enter, telemetry, expected torque states, and follower tracking are still checked. **Fault exits remain immediate:** `STOP` or `QUIT` and Enter, Ctrl+C, SIGTERM, console EOF, telemetry faults, tracking errors, and earlier-stage deadlines end the experiment without waiting for confirmation. After this program has attempted its first motor write, cleanup independently attempts torque OFF with readback on **every joint on both buses**, then closes both serial ports. Physical support remains necessary if communication fails. Check `cleanup_verified`; `cleanup_failed` means torque release or port closure could not be verified.

The console shows separated Chinese operation prompts only at stage changes; it does not print periodic telemetry/status lines. Wait for the explicit `4/5 READY` prompt before moving the gripper; the baseline message is not readiness. Full samples remain in `events.jsonl`.

The console is polled without blocking telemetry. `ARM` and `GO` each have a 60-second wait deadline. Alignment has a 45-second deadline, and the baseline/trigger wait has a 30-second deadline (`--command-timeout`, `--align-timeout`, `--ready-timeout`). An out-of-order command does not advance the state. Supply each command only at its printed prompt; do not pipe a prerecorded sequence.

## Pose and continuity conventions

The five arm joints use the installed LeRobot `DEGREES` convention: `(raw - calibrated_range_midpoint) * 360 / 4095`. Each arm has its own range midpoint and stored hardware homing offset. Raw telemetry already includes the hardware offset, so it is not applied again. The leader and follower therefore receive different raw targets for the same calibrated angle. Only the inspected `drive_mode=0` convention is accepted. Matching calibrated joint angles does not establish collision-free Cartesian movement; the operator must clear the swept path.

The gripper uses each arm's calibrated `0..100` percent range. Its physical opening is **not aligned** during `GO`, since it must remain free for triggering. At takeover, the first follower command exactly repeats the held raw targets, including the gripper. The five arm joints retain a fixed trigger-time offset:

```text
arm_target = held_follower_goal + (current_leader_angle - leader_angle_at_trigger)
```

This preserves the first arm command despite residual alignment error. Arm targets outside either calibrated range still abort.

The gripper then uses incremental opening changes:

```text
desired_opening = previous_commanded_opening + (leader_opening - previous_leader_opening)
target_opening = clamp(desired_opening, 0, 100)
target_opening = max(target_opening, measured_follower_opening - closing_lead)
```

`--gripper-closing-lead` defaults to **3 percentage points**. This is a position cap that limits how far a new closing target leads the measured follower opening when the follower lags, such as while holding an object. The existing speed and per-cycle limits are then applied to the command. If an existing command is already beyond the measured-position cap, it moves back toward the cap within those same step limits; an immediate jump is avoided, so the actual commanded gap can temporarily exceed three points when measured position changes unexpectedly. Opening input immediately raises the commanded opening, including when the prior closing command still leads the measured follower opening.

The latest leader opening is consumed on **every** cycle, including when the range, closing-lead, or step limit caps the command. Excess leader travel is discarded, so it does not accumulate and need to be undone before reversing direction. The gripper therefore no longer maintains a fixed offset from its trigger-time opening. Speed-limited travel is also discarded. Use small, slow strokes; after a limit is reached, open and close it again to supply new relative movement. Invalid or out-of-calibration **measured telemetry** still aborts; only the gripper's requested target is capped.

The cap uses position feedback only. It does not detect contact, measure gripping force, or limit physical force. Existing torque-state, tracking, telemetry, communication, and reported servo errors remain abort conditions. Use a supported, clear setup; holding an object is not evidence that the gripping force is safe.

Leader alignment defaults to eight degrees/second. Follower updates default to 30 degrees/second for arm axes and 30 percentage points/second for the gripper. Both use a maximum 1.5-unit change per cycle (`--align-speed`, `--follow-speed`, `--max-step`). These bounds constrain requested positions, not measured physical velocity or force. Measured tracking error greater than eight degrees or gripper percentage points aborts (`--tracking-error`); the leader also has to remain within the alignment tolerance while waiting for the trigger. Telemetry must be finite, inside calibration limits, have the expected torque states, and arrive within the 0.5-second gap limit (`--max-gap`). Pose stability and telemetry freshness are rechecked before enabling each joint.

## Evidence and offline verification

Every invocation defaults to a unique timestamp/UUID evidence directory under `/data/work/so101-evidence/real-robot/handover-*`. `events.jsonl` records settings, both calibration maps, raw and normalized telemetry, state transitions, alignment error, baseline, trigger references, follower commands, failures, and cleanup readbacks. `teaching_stopped` marks the final hold, and `release_confirmed` records the explicit Enter. Gripper command entries include `gripper_caps`: `range`, `closing_lead`, and/or `step` when a requested change is limited. `--evidence-dir` can override the directory; an existing `events.jsonl` is never overwritten. No video is recorded.

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest tests/test_leader_follower_handover.py tests/test_leader_push_probe.py -q
```

The tests exercise differing arm calibration midpoints, initial torque/calibration/port rejection without writes, current-pose hold ordering, bounded alignment, measured non-convergence, explicit commands and deadlines, gripper-triggered release, continuous first commands, bounded subsequent tracking, interrupt cleanup, and partial cleanup failure. They also replay the 103 gripper samples from the failed `handover-20261105-213637-a1f9f843` trial, test opening/closing reversal at 0/100 percent and under measured position lag, and verify that spikes remain step-limited while arm range violations still abort. They never open serial hardware. Plugin autoload is disabled because this machine's unrelated ROS pytest plugin requires an unavailable `lark` package.

During alignment, `alignment_diagnostic` records the leader goal registers, positions, raw load, and raw current about once per second. These are diagnostic counts, not calibrated forces. They stay in the evidence file and do not change gains, torque limits, or alignment tolerances.



## Bounded stable approximate alignment

`--approximate-alignment` accepts a stable residual against the **unchanged nominal follower target** rather than adding a leader goal offset:

| Requirement | Fixed bound |
| --- | --- |
| Leader elbow absolute original-target error | ≤4° |
| Each of the other four arm-joint errors | ≤1.5° |
| Continuous five-axis stable window | ≥1 second |
| Each joint's peak-to-peak position in that window | ≤0.35° |

All five nominal goal ramps must finish before the window starts; the sample read before the last ramp command is not counted. Every recorded position in the full window must satisfy its joint's error limit, so an instant crossing into tolerance is insufficient. A sample just before the one-second boundary is retained to cover the complete time interval. These mode-specific bounds are fixed: changing `--converge-tolerance` or `--converge-seconds` cannot loosen or shorten them. The existing initial current-pose enabling checks, calibrated ranges, telemetry freshness, follower tracking checks, and speed bounds remain active.

After this gate passes, the same rolling position and error checks remain active throughout the gripper baseline, `READY`, and trigger sustain. Any error-limit violation or peak-to-peak span above 0.35° causes an immediate fault exit and torque cleanup, before accepting the gripper trigger. The program does not automatically recover or re-arm after this loss of stability. Keep the gripper still until `READY`; then support the leader without lifting, pushing, or repositioning the arm. Arm movement while preparing the trigger can fail this gate even if the elbow remains inside 4°.

At takeover, the first follower raw goal exactly repeats its held target. The leader reference is the latest measured trigger-time pose, including the accepted residual; subsequent arm tracking retains the existing relative mapping. This preserves command continuity without claiming the two physical arms have identical joint angles. No compensation offset or PID/EEPROM changes are applied. This remains a standalone experiment, not production DAgger integration.

Evidence includes `alignment_mode`, per-axis `residuals_degrees` and `tolerances_degrees`, plus `alignment_gate` with window duration, per-axis spans, and limit/stability decisions. `ready_alignment_check` records the same gate before each baseline/trigger evaluation. Normal teaching completion still waits for Enter before releasing the held follower; faults still clean up immediately.

## Opt-in elbow goal compensation experiment

The observed elbow retained an approximately +3.7° error against its original target while held; a later supported run reached the original target and completed teaching. `--elbow-compensation` tests whether a small opposite-signed **goal-position offset** can reduce this residual without external support. It is disabled by default. A subsequent unassisted hardware trial reduced the original elbow error from about 3.824° to 1.89° at the 3° compensation cap, which still exceeded the requested 1.5° tolerance. The cap and tolerance remain unchanged.

```bash
HF_HOME=/data/models/huggingface /data/work/venvs/so101-smolvla-061/bin/python tools/probe_leader_follower_handover.py --converge-tolerance 1.5 --elbow-compensation
```

Follow the same `ARM` and `GO` sequence. Once the leader is powered and moving, withdraw supporting force and do not touch it during alignment, so measured improvement can be interpreted. Keep support nearby for emergencies. Support the leader again when the explicit `READY` prompt appears, before moving its free gripper to release the arm. The console announces compensation start and successful completion, without periodic measurement output.

The experiment affects only the leader's `elbow_flex` goal:

- The normal five-axis ramp must finish first. An elbow residual outside the original convergence tolerance must remain stable for at least one second, with a peak-to-peak span no greater than 0.35°.
- The offset opposes the signed measured error. Its maximum magnitude is 3°, its slew rate is 0.5°/second, and the existing alignment speed/per-cycle command bounds also apply. Raw integer goal rounding adds at most about 0.044° to a desired goal; individual raw steps are quantized to motor ticks.
- A trial adds at most 1° of offset. Within each three-second trial window, the measured absolute error against the **original target** must improve by at least 0.25° before another trial is permitted. A stuck elbow therefore cannot simply wind up to the maximum.
- A measured error increase greater than 0.5° relative to the current trial's starting error, a wrong-sign overshoot beyond the original tolerance, missing progress, exhausting the 3° cap, an out-of-range goal, or an existing telemetry/tracking fault aborts and runs the normal two-arm cleanup.
- Once the measured elbow enters the original tolerance, its offset freezes while the normal convergence dwell is checked. The original target remains the reference for both convergence and `READY`; the offset is held through the gripper baseline and trigger wait. No sudden reset to the nominal goal is commanded. At the trigger, the normal measured leader reference preserves the follower's first held command.

`elbow_compensation` evidence records the original nominal goal, offset, actual position, signed original-target error, and commanded goal each alignment cycle after compensation starts. `alignment` and the existing goal-register/current/load diagnostic entries also include the offset and nominal target. Abort messages distinguish the latest trial improvement from the overall improvement since compensation began and include the applied offset and remaining error. Reaching the cap is reported as cap exhaustion even when the latest trial also showed insufficient progress. The position registers provide a bounded experiment, not force measurement or force protection. No PID gain, torque limit, operating mode, calibration, or EEPROM values are changed; all existing reported-servo-error and cleanup paths remain active.

Offline tests cover successful convergence under a persistent simulated load offset, disabled behavior, rate and magnitude caps, partial-response cap exhaustion, stuck and wrong-direction plants, overshoot, calibrated raw-range rejection before a goal write, and unchanged first follower commands. Approximate-mode tests exercise stable 3.7° acceptance, fixed elbow/other-axis limits, jitter and drift rejection, complete post-ramp windows, old out-of-bound samples, READY stability loss, mutual exclusion, strict-mode rejection, and exact first-command continuity. Final-release tests verify that the follower holds beyond the former time limit, leader motion no longer updates targets, Enter causes cleanup, and a fault during the wait still causes immediate cleanup.
