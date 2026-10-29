# Rename the project to so101_rollout

Status: proposed; execution requires explicit user approval.

Rename the active project identity consistently while preserving robot behavior, dependencies and historical evidence.

| Identity | Current | Proposed |
| --- | --- | --- |
| Checkout | `/home/matianyi/Projects/so101_test` | `/home/matianyi/Projects/so101_rollout` |
| GitHub | `terryma2024/so101_test` | `terryma2024/so101_rollout` |
| Python package | `so101_test` | `so101_rollout` |
| Distribution and console command | `so101-test` | `so101-rollout` |

Python distribution names normalize underscores and hyphens. Use `so101-rollout` in package metadata and the console command, and `so101_rollout` for imports and the repository.

## Approach

Use a coordinated rename: update source and active documentation in an isolated worktree, validate the package, move the stable checkout, repair installed paths, and rename GitHub after local validation. A folder-only rename would leave the import and command identity unchanged. Keeping aliases would add another supported interface without an identified consumer. The proposal therefore introduces no old-name alias.

## Scope and preservation

- Move `src/so101_test/` to `src/so101_rollout/`. Update imports, shell module targets, packaging, lockfile project metadata, tests, greeting and current README commands/paths. Preserve all dependency versions and lockfile resolution data.
- Rename the project-specific evidence switch in `tests/conftest.py` to `SO101_ROLLOUT_EVIDENCE_RUN_DIR`, and use that name for subsequent controlled runs.
- Keep root compatibility script filenames, hardware configuration, calibration, model/dataset/policy names and runtime arguments unchanged.
- Keep previous plans, ledgers, commit history, recorded paths, old build artifacts and evidence intact. Update current ledger header paths after the move; append migration facts without rewriting historical entries.
- Preserve the root `.venv` and both managed environments. Replace only the project distribution in `/data/work/venvs/so101-real-lerobot-061/` and `/data/work/venvs/so101-voice-lerobot-061/`. Repair the root environment's old absolute paths and reinstall its renamed editable project without dependencies. Snapshot and verify every other distribution remains unchanged.
- Preserve retained worktrees and repair their Git administrative paths after moving the main directory. Do not delete environments, worktrees or evidence.

## Verification and rollout

Reuse launcher, entry-boundary, config and package provenance tests with the new names. Run the full ordinary `tests/` suite with `min(8, os.cpu_count() or 1)` xdist workers, unique NVMe scratch and independent controller/worker tempfile proofs. Verify final stable-path imports, entry scripts, editable metadata and managed wheel bytes from outside the checkout. Run only help, greeting and existing fake/stub paths; this rename does not require hardware, model downloads, benchmarks or a GUI.

The coordinator performs GitHub's repository rename through its REST API after local validation, using available authorized credentials without logging secrets, then updates `origin` with standard Git and verifies repository identity and advertised refs. Read-only preflight confirmed repository ID `1434336506`, authenticated administrator access and availability of the new name. No `gh` CLI or force push. The seven local commits already ahead of `origin/main` require a separate explicit publication decision; the rename does not authorize pushing them. Until publication is requested, GitHub retains its existing source commits under the new repository name.

Evidence root: `/data/work/so101-evidence/project-rename/20261029-so101-rollout/`. Record external artifact paths and SHA256 hashes there. Build artifacts belong under `/data/work/so101-build/project-rename/20261029-so101-rollout/`. Preserve rollback artifacts and classify scratch as deletion candidates after readback, without deleting it.

Rollback restores the previous project wheel/editable metadata and recorded environment files, reverses the checkout move and worktree repair, and, if necessary, renames GitHub back after checking the old name remains available. Preserve all unrelated work and remote commits. Stop on an unexpected concurrent writer, dirty worktree, installation drift or insufficient GitHub permission.
