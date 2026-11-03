# SmolVLA v2 local execution implementation plan

> For agentic workers: use superpowers:executing-plans. The user explicitly authorized immediate execution and local formal training after all gates.

Goal: export 262 train / 76 validation episodes, verify immutable source identity and train-only stats, run 100 batch32 smoke steps and strict CPU reload, then start a fresh official-base 20k local run.
Architecture: new v2 exporter extends the reviewed v1 functions without changing v1 behavior. Selection uses complete original source groups; B02/G19 is excluded and replaced by the accepted new source ep0. Frozen source snapshots and receipts bind the local launcher.
Tech Stack: existing offline LeRobot 0.6.1 / Torch 2.11 ML environment, pandas/pyarrow/PyAV, Python/Bash.
Spec: docs/plans/smolvla-data-first-v2-20261102.md, latest explicit local execution authorization.

## Global constraints
- Preserve all original datasets, v1 outputs and existing dirty changes. No push or hardware use.
- Use official base revision 5e8d12a6e2975b0e5e5fce7c8caf47c371d257b6 and pinned VLM revision 7b375e1b73b11138ff12fe22c8f2822d8fe03467; no resumed v1 weights.
- FP32/no AMP, frozen vision/expert-only/state projection; batch32, seed1000, 20k steps, AdamW1e-4, preset cosine, full validation/checkpoints5000.
- No formal GPU launch before CPU approval, smoke100, actual weight update, strict reload and frozen file/environment checks.

## Review focus
- Excluding an episode in a shared v3 video must remove its segment and reindex subsequent episodes correctly.
- Existing clean-source origin mapping and two-color same-session group identity must survive export.
- Manifest counts, source numeric identity and train-only normalization must be checked against real loader output.
- Local approval cannot depend on fictitious remote transfer receipts.
- Launcher must refuse changed artifacts, reused output paths, duplicate trainers and GPU contention.

## Task 1: v2 selection and export
Files: tools/prepare_smolvla_v2_data.py, tests/test_smolvla_v2_data.py.
Interfaces: build_records(base, old_records, selection) -> records; export CLI emits split.json, episode-map, source SHA receipts, stats and dataset approvals.
- [x] Write and observe failing tests for exclusion/replacement/source groups and malformed selections.
- [x] Implement v2 exporter, preserve old records, selected-source views via upstream delete_episodes, independent outputs.
- [x] Run tests and export actual data, verify every selected episode numeric identity, source unchanged, loader first/last and videos, direct recomputed stats.

## Task 2: frozen local run preparation
Files: tools/run_smolvla_v2_local.sh, tools/guard_smolvla_v2_local.py, tests/test_smolvla_v2_local.py.
Interfaces: local evidence has data approval, source/model/environment manifests, smoke/final configs and new output directories.
- [x] Write and observe failing guard tests for changed artifacts and approval mismatches.
- [x] Implement local guard/launcher, reusing content/split helpers and no remote-only requirement.
- [x] Prepare real offline config and receipts; run related + full CPU tests; request parent independent review.

## Task 3: GPU smoke and formal start
- [x] Recheck GPU ownership and acquire same GPU lock for smoke.
- [x] Run batch32/100 steps from base, record finite losses/gradients/tokens/colors/memory and updated model weights.
- [x] Strict CPU checkpoint reload and train-fitted processor equality.
- [x] Freeze approvals and launch fresh local20k under lock; verify running process and actual step log.

## Execution ledger
Ruling: work in the user-authorized shared checkout with new v2 files only, then freeze an independent evidence/source snapshot. A git worktree at HEAD would omit the required untracked v1 training tools; do not stage or commit unrelated dirty material.

Task 1: complete — exporter tests RED then GREEN (10 passing with v1 data tests); real export CPU approved 262/75880 train and76/23145 validation, source hashes unchanged,338 actual episodes loader boundaries and all videos decoded.
Task 2: local guard tests RED→GREEN; full suite478 passed before FP32 wrapper, final suite running. Official base and runtime native dtypes are BF16/F32; .float() is required to satisfy the explicitly specified FP32 contract. New v2 wrapper changes no legacy adapter code; BF16→F32 conversion is lossless but differs from v1 native mixed-dtype behavior. CPU strict reload and processor save/reload pass, environment115 packages compatible.
Task 3: smoke running under GPU flock with b32/100steps, full val, all policy weights explicitly FP32.

Review correction: latest source plan explicitly assigns replacement to logical B02 group; capture_group now enforces that while preserving independent physical source/origin. New split-b02-corrected.json CPU revalidated actual sources/data trees and config was regenerated; original history is retained. Corrected-manifest second100-step smoke+CPU reload passed; all155 trainable tensors changed and no frozen tensors changed. Its model.safetensors SHA equals the initial full-val probe exactly, so the same weights and data tree have complete23145-frame held-out coverage. Second smoke itself uses32 frames/color. maxallocated11253664256/maxreserved12303990784 bytes. Final formal verifier requires all four5000-step full evaluations and checkpoint training_state step/batch plus all-F32 weights.

Task 3: complete for authorized launch milestone — two real100-step b32 runs, strict CPU reload/update proof, full validation same-weight proof, independent review and484-test suite passed.3112-artifact freeze and real local preflight passed; formal launcher4035292/trainer4035410 running, verified step34 finite. Formal20k has not completed; its configured final verifier runs automatically after all steps.
Final preflight ruling: clear inherited ROS PYTHONPATH in the launcher to match isolated115-package ML inventory used by smoke; initial inherited297-package guard rejection is retained as evidence.
