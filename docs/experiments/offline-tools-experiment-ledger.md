# Offline experiment tools migration

- Task: retain the SO101 rollout review and collection workflows as reusable repository tools.
- Worktree: `/home/matianyi/Projects/so101_rollout`, branch `main`, base `5cc17c7d92ae16ca233451579dd78508e9b511c3`.
- Evidence root: `/data/work/so101-evidence/real-robot/p0-20261029T215724/`; migration artifacts in `tools-migration/`.
- Scope: offline utilities, reviewed annotation/collection inputs, documentation and tests. Existing user-authorized `AGENTS.md` image rules retained. No robot/camera execution, training, dataset merge, print, commit or push during migration.
- Workflow: root handles user discussion, choices and acceptance; user explicitly authorized SubAgents for complex/long tasks. Delegated legacy tools and documentation to separate writers and a read-only correctness audit; root integrated changes and verified them.

## Delivered interfaces

See `tools/README.md`: dataset integrity/light/contact sheets; human outcome aggregation; calibrated cube estimates; P0 seven-page record sheets; colour-separated collection cards; preview/SHA256/explicit printing; physical-colour language-pair planning audit. `tools/source-provenance.json` records historical scripts and hashes.

Small JSON files in `tools/plans/` are input plans and explicit human annotations, not generated image/video evidence. P2 preserves all80 printed conditions, four independent dataset names and exact task labels. Raw source data and historical helper versions remain in evidence.

## Verification

- Initial regression: four intended failures for missing migrated utilities; new language pairing regression failed before implementation. Review fixes reproduced manifest overwrite, output escape/collision, mismatched recording root, colour/ID mismatch, nonboolean exclusion and invalid/empty metadata before correction.
- Targeted final tools tests:18 passed (15 core +3 legacy).
- Full ordinary repository tests:259 passed,0 failed/errors/skipped, xdist8 on32 CPUs, exit0. Command/result/JUnit and controller/worker tempfile placement proofs: `tools-migration/full-6f877keg/`. Tool interpreter `/data/work/venvs/so101-rollout-tools/bin/python`; separate from robot runtimes.
- Real-data replay: all6 P0 datasets /61 raw episodes /22775 frames pass metadata, timestamp, index, finite action/state and both camera-count checks. Single-frame green-r2 ep7 remains retained/flagged. The explicit outcome annotations reproduce46/60 successes (green26/30, red20/30). Files: `dataset-checks.json`, `reproduced-summary.json`, `review-*/`.
- Calibrated start-cell estimates for green-r1 match historical output. Calibration/HSV remains heuristic and does not classify success.
- Rendered all80 cards into4 colour-separated batch PDFs /5 A4 pages. Independent P0 renderer produced7 A4 pages. Preview dimensions inspected before viewing; previews<=1600; red bold nonzero shifts/angles retained. Outputs remain external.
- Read-only audit findings corrected with regressions. Review now stores sampled thumbnails plus first/last frames instead of all decoded frames. Recording card roots are restricted to the actual fixed `record.sh` root. Output manifests cannot replace source files; batch IDs cannot escape output paths.

## SmolVLA goal and coverage

User goal: one SmolVLA selects red/green from instruction. Current ACT files remain separate; a future derived multi-task dataset must retain both task labels. If all80 additions are accepted, expert totals are133 green +132 red =265; the60 P0 evaluation trials are not expert training data.

The new80 planned records alone have12 physical cell-pair conditions, only1 represented under both instructions (6 demonstrations); including offsets/angles,51 conditions with1 paired (3 demonstrations). These are planning statistics, not an audit of all265 accepted demonstrations or identical camera scenes. Do not label all data sufficient for reliable language control without checking original records and evaluating fixed-scene instruction swaps. Official source consulted: https://huggingface.co/docs/lerobot/en/smolvla (starting point around50 demonstrations, variation coverage required).

## Retention and next step

Retain all original evidence, migrated tools, plans, tests, generated validation outputs and test logs. Archived:NONE. No deletion authorized or performed. Future collection should use `tools/record-p2-20261030.txt`; annotation/quality review precedes separate ACT training or any SmolVLA multi-task export.
