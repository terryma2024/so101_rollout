# Bounded stable approximate handover alignment

The user approved continuing the standalone takeover experiment with bounded stable approximate alignment, rather than trying additional elbow goal compensation. Earlier evidence showed an approximately 3.7° elbow residual at its nominal holding target. A compensation trial improved error but exhausted its 3° goal-offset cap before meeting the 1.5° criterion. This change does not alter those historical records or production DAgger code.

The explicit `--approximate-alignment` mode applies no goal compensation and cannot be combined with `--elbow-compensation`. It accepts elbow original-target error≤4° and each other arm-axis error≤1.5°, only after the nominal ramp finishes and every axis remains within its limit with position peak-to-peak≤0.35° over a full continuous second. These bounds are fixed, independent of the strict mode's configurable tolerance/dwell.

The stable window stays active during the gripper baseline and trigger wait. Losing any bound or stability check aborts before triggering and uses immediate existing cleanup. This deliberately chooses a simple fail-closed response, with no automatic re-arming. The operator must support the arm at READY without lifting or pushing it. Trigger-time measured leader references and the exact first follower raw goals preserve the existing relative takeover mapping. The final Enter-to-release hold and immediate fault cleanup are unchanged.

Offline fake-bus and gate tests validate stable 3.7° residual acceptance through teaching, fixed limits that cannot be widened by strict-mode settings, jitter/drift rejection, window coverage and old-sample checks, loss of READY stability, strict-mode behavior, mutually exclusive flags, and first-command continuity. No hardware run or PID/EEPROM edits were performed for this change. No commit was created.

```bash
HF_HOME=/data/models/huggingface /data/work/venvs/so101-smolvla-061/bin/python tools/probe_leader_follower_handover.py --approximate-alignment
```
