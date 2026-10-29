# SO101 Rollout Rename Implementation Plan

> **For agentic workers:** Use `superpowers:subagent-driven-development` with the user's chosen Sol High implementer and inline self review. Do not execute before explicit approval of this plan.

**Goal:** Rename the active local and GitHub project to `so101_rollout` and verify its existing workflows still resolve the intended code.

**Architecture:** Rename the canonical package and its callers as one mechanical change. Validate in isolation, move the stable checkout and repair environment/worktree paths, then rename GitHub and update the Git remote.

**Tech Stack:** Python 3.12, uv/uv_build, pytest-xdist, Git, GitHub REST API.

**Spec:** `docs/superpowers/specs/2026-10-29-so101-rollout-rename-design.md`

## Global constraints

- Execution requires explicit user approval. Use Sol High with inline self review under the user's preserved execution preference.
- Stable path: `/home/matianyi/Projects/so101_rollout`; package: `so101_rollout`; distribution/command: `so101-rollout`.
- Evidence: `/data/work/so101-evidence/project-rename/20261029-so101-rollout/` (E below). Build/wheel output: `/data/work/so101-build/project-rename/20261029-so101-rollout/` (B below).
- Preserve dependency versions, runtime behavior, hardware configuration, historical documents/artifacts, worktrees and all user changes. No new aliases, hardware execution, benchmark suite, `gh`, force push or evidence deletion.
- Local main starts at `424d1ded82e0d11b8b26747fcc2b84c0a9bef1e8`, seven commits ahead of origin/main. No push without an explicit publication decision covering those commits.
- Every pytest invocation gets a fresh E/scratch run, exact-Python tempfile preflight and recorded exit/elapsed/JUnit results. Full ordinary tests use xdist with `min(8, cpu_count)` workers.

## Review focus

1. Stale imports masked by cwd: reuse external-cwd provenance probes in Tasks 1 and 2.
2. Moved `.venv` with stale shebangs/editable URLs: run actual entry scripts and inspect exact metadata at the final path in Task 2.
3. Unrelated dependency drift during installation: compare distribution snapshots excluding only old/new project names in Task 2.
4. Retained nested worktree references: verify `git worktree list --porcelain`, `.git` pointers and clean status in Task 2.
5. GitHub redirect mistaken for a rename or accidental publication: compare immutable repository ID/full_name and advertised refs before/after in Task 3.

### Task 1: Rename the canonical package and validate the isolated checkout

**Files:** Move `src/so101_test/` to `src/so101_rollout/`; modify `pyproject.toml`, `uv.lock`, `README.md`, the eleven root Python delegates, `scripts/{voice_agent,record,teleop,camera_settings}.sh`, existing affected `tests/test_*.py`, and the evidence switch in `tests/conftest.py`. Create/update only this task's ledger under `docs/experiments/so101-rollout-rename-experiment-ledger.md`.

**Interface:** Produce `so101_rollout.{voice,camera,operations,config}` and `so101-rollout = "so101_rollout:main"`, with greeting `Hello from so101-rollout!`. All existing callable signatures remain unchanged.

- [ ] Recheck source/remote refs, all worktree status, executable paths and live processes. Snapshot distributions and affected root `.venv` path-bearing files under E. Register any external artifacts by path and SHA256. Read applicable worktree skill; create an isolated implementation worktree only after approval.
- [ ] Record a negative smoke probe for the new package/command on the original installation. This is a naming precondition, not a source regression. Reuse existing meaningful boundary tests; do not add tests that merely mirror string replacement.
- [ ] Apply the scoped rename above. Search tracked active files for `so101_test`, `so101-test`, and `SO101_TEST`; classify remaining references as historical or unintended. Keep prior plans/ledgers unchanged. Review lockfile diff: only local project identity may change.
- [ ] Install only the renamed editable project into the selected development environment using its exact Python and `uv pip install --no-deps --reinstall -e <implementation-worktree>`. Reuse existing pytest/xdist; if unavailable, report the dependency gate rather than silently changing environments.
- [ ] Run focused `test_package_provenance.py`, `test_launchers.py`, `test_entry_boundaries.py`, and `test_config.py` in controlled scratch. Then run the full existing `tests/` scope with the gate below. Read logs/JUnit and inspect source/package/entry-point provenance. Inline self review, `git diff --check`, then commit the scoped rename and documentation.

### Task 2: Deploy locally and move the stable checkout

**Files:** Root `.venv` path-bearing launch/activation/config/install metadata; retained Git worktree administrative files; renamed stable checkout; project distributions only in the two existing managed environments. No dependency source changes.

**Interface:** Produce a working stable checkout at `/home/matianyi/Projects/so101_rollout`, with editable development imports from that root and immutable wheel imports in both managed environments.

- [ ] Fast-forward the stable checkout to the reviewed rename commit, preserving other commits and checking all worktrees again. Build the wheel under B with uv's build output directed there; record command, manifest and SHA256 in E. Preserve previous wheel artifacts and their hashes for rollback.
- [ ] Preflight both `/data/work/venvs/so101-real-lerobot-061/bin/python` and `/data/work/venvs/so101-voice-lerobot-061/bin/python` with `test -x`. Remove only `so101-test`, install the new wheel with `uv pip install --python <exact-python> --no-deps <wheel>`, then compare every other installed distribution to its snapshot.
- [ ] Before moving, verify the destination is absent and no running workload relies on the old path. Preserve active coordinating sessions; move from a neutral working directory without terminating unknown processes. Move the main checkout to the target path, keeping its nested retained worktrees and `.venv`.
- [ ] Run `git worktree repair` from the new main path with the moved retained worktree paths. Verify their `.git` pointers, branches, HEADs, status and main Git directory; do not prune or delete worktrees.
- [ ] Repair the root `.venv` narrowly. Use the backed-up inventory to rewrite the exact old checkout prefix in text launcher shebangs, activation scripts and venv configuration, and update the prompt to `so101-rollout`. Replace the old project distribution with a `--no-deps` editable install of the final stable path. Update affected RECORD hashes/sizes for repaired third-party launchers; preserve every other package file. Inspect hidden/ignored environment files explicitly with `rg --hidden --no-ignore`. Stop if unclassified binary or external absolute references require another strategy.
- [ ] From an E-owned neutral cwd with overlay variables cleared, reuse the renamed `PROVENANCE_PROBE` from `tests/test_package_provenance.py`: development mode expects the stable source root; each managed mode expects its site-packages package, the wheel path and its independently computed hash. Verify absence of installed old project distribution and old package imports. Run the actual `.venv/bin/pytest --version` and `.venv/bin/so101-rollout`, plus harmless module `--help` and existing fake/stub commands. Confirm launcher shebangs and activation resolve the new root.
- [ ] Run the full ordinary suite once at the final stable path using the gate below; compare counts to the isolated run (baseline currently 241 tests). Recheck all distribution snapshots, old-path references and worktree status. Update current ledger header/checkpoint paths while preserving historical entries. Inline self review and record local rollout result before external mutation.

### Task 3: Rename GitHub and verify the final state

**Files:** Git remote configuration and task ledger only; external GitHub repository name.

**Interface:** Preserve the same GitHub repository ID under `terryma2024/so101_rollout`, with `origin = git@github.com:terryma2024/so101_rollout.git`.

- [ ] Coordinator confirms authenticated permission and the target name is available, records the original repository ID/full_name/default branch and remote refs. Use a secure API client that does not expose tokens in argv, logs or evidence. If access is unavailable, report the precise blocker and retain the validated local result.
- [ ] After local validation, coordinator performs `PATCH /repos/terryma2024/so101_test` with `{"name":"so101_rollout"}`. Read back the new endpoint; require unchanged repository ID and exact new full_name. Record only sanitized response fields.
- [ ] Run `git remote set-url origin git@github.com:terryma2024/so101_rollout.git`, inspect fetch/push URLs, and verify `git ls-remote` against the new repository. Repository rename must preserve advertised branch/tag commits. Do not push the seven earlier local commits or rename commits without the user's explicit publication decision; fetch and preserve any remote-only commits if publishing is later authorized.
- [ ] Record final commit/path/environment/API verification and ahead/behind state. Report retained runs, archived runs (none unless explicitly created), and deletion candidates (scratch and backed-up superseded environment files); delete nothing. State clearly whether source commits have been published.

## Controlled pytest gate

For each run, resolve the exact development Python, verify `pytest` and `xdist` origins/versions, and record CPU count, memory and competing load. Allocate a unique `E/scratch/pytest.XXXXXXXX` with `mktemp -d`; create its `tmp/`; set `TMPDIR`, `TMP`, `TEMP` to that directory and `SO101_ROLLOUT_EVIDENCE_RUN_DIR` to the run directory. With that exact Python, assert `Path(tempfile.gettempdir()).resolve() == Path(os.environ['TMPDIR']).resolve()` before invoking pytest. The original installation's negative/baseline checks use its existing `SO101_TEST_EVIDENCE_RUN_DIR` switch until the source rename is applied.

Run `"$TEST_PYTHON" -m pytest tests/ -n "$workers" -o tmp_path_retention_policy=failed -o cache_dir="$pytest_run_dir/pytest-cache" --junitxml="$pytest_run_dir/junit.xml"`, redirecting output to the run log. Preserve the actual exit code and elapsed time; if introducing a pipeline, enable `set -o pipefail`. Read JUnit counts/skips and confirm controller plus every worker wrote tempfile proof under that run. A narrowed or serial run does not replace this gate. All retries retain the original failed run and receive a new scratch directory.

## Recovery

If any deployment step fails, inspect processes, logs and declared outputs before retrying. Restore only changed project installations and backed-up environment path files; reverse the checkout move and worktree repair if required. If GitHub was already renamed, inspect both names and repository ID before reversing it. Never overwrite concurrent work, force push, remove environments or delete evidence to recover.
