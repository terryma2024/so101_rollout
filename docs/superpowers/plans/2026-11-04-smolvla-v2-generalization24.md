# v2 泛化24条执行包计划

> For agentic workers: use superpowers:subagent-driven-development. User selected the proposed 24-trial quick screening; prepare the existing finite-session workflow without another approval loop. No hardware execution by agent.

**Goal:** Freeze a 24-trial operator-run package for v2 20k, 8 baseline and 16 novel-combination trials.

**Architecture:** Reuse existing baseline package generator/session entry without changing runtime behavior. A task-owned preparation script/manifest creates fresh datasets and records, documentation from the same ordered plan. Model loads once; each trial retains local Enter and preflight.

**Tech Stack:** Python existing repository tooling, pinned so101-smolvla-061 environment.

**Spec:** User approved quick screening: A and B groups only, two repetitions of every layout/color condition. Baselines G C2/R C3 and G C3/R C2; novel G B2/R B3, G B3/R B2, G B1/R C3, G C3/R B1. All cube centers at nominal grid center, zero yaw, no offsets. Fixed bowl/cameras/light and approved initial arm/wrist/gripper pose. Composition generalization, not certified out-of-spatial-support extrapolation.

## Constraints and review focus

- v2 020000 SHA 16d9116230bf5bb8eba4f6a9c9bbf635df9f3d93869b04da3f66252ce3e44b85; do not accidentally use v1/v3 generator default.
- 20Hz hard async, horizon50/prefetch10/maxrel30, 30 seconds, one episode per trial.
- 2 rounds of12, each contains all6 layouts and both color instructions; reverse color order across rounds and intersperse baseline layouts. Restore cubes between paired instructions.
- Distinct fresh paths, refuse overwrite, preserve failed trials and operator stop/return behavior. No robot/camera/GPU usage during preparation.
- Existing dirty repo stays intact; no commit or push required. This is artifact configuration, not a runtime feature.

## Task 1: Prepare and verify

- [ ] Read generator/session interfaces and existing v2 package.
- [ ] Create task-specific reproducible preparation entry under tools/ and fresh evidence package under smolvla-v2-generalization24-20261104; use existing launcher semantics.
- [ ] Generate plan, blank results, collect.py and Chinese INSTRUCTIONS from the same trial order. Include per-trial layout/target and exact invocation, no manual model loading.
- [ ] Validate 24 cases, each layout/color exactly twice, balanced colors and rounds, exact model/hash/parameters, fresh paths and matching documentation.
- [ ] Run dry-run and structured native config parsing with CPU/no devices; verify no dataset or execution artifacts created. Save package verification receipt.
- [ ] Root independently check outputs and deliver full sequence plus command. No printing or hardware launch without user request.

## Outcome measures

Target-color final in bowl / all attempts; first observed stable lift color / stable-lift attempts, with no-lift count separate; first-attempt lift, retries, wrong-color deposit, elapsed time, safety stops. Report baseline and each novel layout/color separately. Two trials per condition are screening, not a reliability estimate; failed attempts remain in denominator. Test episodes are not training demonstrations.
