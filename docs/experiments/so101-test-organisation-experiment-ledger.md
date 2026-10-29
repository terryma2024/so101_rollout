# so101_test organisation experiment ledger

```yaml
task_id: so101-test-organisation-20261029-e8a252c0
goal: organise the application in its existing src package without robot behaviour changes
success_contract: approved migration; baseline and final full tests with min(8, CPU) workers; installed provenance in three environments
worktree: /home/matianyi/Projects/so101_test/.worktrees/repo-organisation
branch: chore/so101-test-organisation
base_commit: c724e389536e56875a54642b230d48532dfbde35
current_commit: Task 2 checkpoint containing this ledger; exact SHA recorded in evidence task2-report.json
evidence_root: /data/work/so101-evidence/repo-organisation/20261029-e8a252c0
confirmed_conclusions:
  - approval document hashes match execution-approval.json (CP-001)
  - original main was clean except approved planning documents (CP-001)
  - all 146 original tests pass with eight workers after removing inherited ROS overlay variables in the test subprocess (GATE-002)
  - existing application dependencies are unchanged in all three environments (CP-002)
disproven_routes:
  - running this non-ROS gate with inherited ROS PYTHONPATH is invalid (GATE-001)
open_hypotheses:
  - NONE
latest_checkpoint: CP-003
next_experiment: Task 3 voice migration
```

The coordinator owns sequential handoffs; the active task executor is the sole ledger writer. Task 1 executor: GPT-6.1 Sol / High implementation subagent. Execution is local on ai-station. No SSH, hardware, cameras, ASR, policy loading, API requests, ROS or GUI runs are included. ROS domain, Gazebo partition, overlays and physical/visual outcomes are N/A because this is a source-only LeRobot task.

## CP-001: approved isolated checkout

- Approval: `execution-approval.json` in the evidence root. Both original document byte counts and SHA256 values verified before mutations.
- Preflight: `task1/preflight.json` records host, cwd, Git/worktree/submodule state, process names, tmux sessions, CPU, memory and load. Existing processes are preserved; this task owns no services.
- Original checkout: `/home/matianyi/Projects/so101_test`, `main`; commit `a137842` contains only approved documents and the `.worktrees/` ignore rule.
- Native worktree tooling is attached to the unrelated host task repository and cannot select repository/path/branch. The approved explicit Git fallback created the registered worktree after checking ignore and branch/path absence.
- Build root: `/data/work/so101-build/repo-organisation/20261029-e8a252c0` (reserved; no build yet).
- Exact test Python: `/home/matianyi/Projects/so101_test/.venv/bin/python`; runtime environments remain read-only in Task 1.
- Owned processes: NONE. Preserved processes: all pre-existing processes in preflight.

## GATE-001: original full ordinary test baseline

```yaml
status: INVALID
prior_experiment: NONE
hypothesis: original tests pass with the exact project Python and required xdist parallelism
prediction: all tests/ collect and execute; controller and eight workers prove NVMe tempfile placement
single_variable: missing test-tool provisioning and opt-in evidence instrumentation only
lifecycle: N/A (headless tests; no robot stack)
preconditions:
  - approved isolated source checkout; original root sys.path fixture retained
  - application dependency versions unchanged; runtime environments read-only
success_criteria:
  - complete tests/ scope; eight workers; exit zero; JUnit and per-process scratch proof read back
invalid_criteria:
  - dependency/collection/setup failure or scratch/provenance failure
provenance:
  source_commit: a137842 plus pending Task 1 evidence instrumentation
  install_overlay: N/A
  runtime_executable: /home/matianyi/Projects/so101_test/.venv/bin/python
  ros_domain_id: N/A
  gz_partition: N/A
decision: REPEAT
next_experiment: GATE-002
```

## Retention

- Retained: the registered evidence root, its original approval/inputs, Task 1 preflight and subsequent gate records.
- Archived: NONE.
- Deletion candidates: NONE before test scratch readback. No evidence or worktree deletion is authorised.

Task 1 pre-gate closure: `task1/paths.json` resolves uv and exact interpreters; `dependency-invariance.json` proves every existing package unchanged. Only pytest 9.2.0, pytest-xdist 3.8.0 and four missing support packages were added to the stable project environment. Real/voice snapshots are identical. `task1/helpers.json` records external helper paths and hashes. Hook verification covers opt-out, distinct process proofs and fail-closed mismatch. `task1/resource-audit.json` records test isolation and host capacity. Voice help/defaults were captured with runtime imports/actions denied; zero denied attempts. Source AST and launcher snapshots are in `task1/source-baseline/`.

GATE-001 result: INVALID environment setup, exit 3, elapsed 0 s, collected/executed 0, no JUnit created. Inherited ROS Python paths exposed the `launch_testing` plugin; its import failed on missing `lark` before collection. Evidence: `scratch/pytest-baseline.YvUPD9KY/` and `task1/baseline-plugin-diagnosis.json`. This is not source RED. No source/product repair and no dependency additions are justified. All processes from this command ended.

## GATE-002: isolated original full ordinary baseline

```yaml
status: VALID
initial_status: PLANNED
prior_experiment: GATE-001
hypothesis: inherited ROS import paths caused the pre-collection plugin failure
prediction: removing ROS overlay variables only from the gate subprocess removes ROS plugins and permits original tests/ collection
single_variable: unset PYTHONPATH, AMENT_PREFIX_PATH and COLCON_PREFIX_PATH for the non-ROS gate
lifecycle: N/A (headless tests; no robot stack)
preconditions:
  - unchanged application source and exact project Python
  - eight workers and fresh NVMe scratch with exact-interpreter proof
success_criteria:
  - complete tests/ execution, exit zero, JUnit and nine controller/worker proofs
invalid_criteria:
  - collection/setup/provenance failure
provenance:
  source_commit: a137842 plus Task 1 evidence instrumentation
  install_overlay: N/A (ROS variables removed)
  runtime_executable: /home/matianyi/Projects/so101_test/.venv/bin/python
  ros_domain_id: N/A
  gz_partition: N/A
commands:
  - clean-gate-plugin-proof.json confirms ROS paths/plugins absent and xdist available
status_before_launch: RUNNING
final_status: VALID
exit_code: 0
collected: 146
executed: 146
passed: 146
failed: 0
errors: 0
skipped: 0
workers: 8
logical_cpus: 32
elapsed_wall_s: 1
elapsed_junit_s: 1.244
controller_worker_proofs: 9
decision: KEEP
next_experiment: Task 2 focused RED gates
command_record: scratch/pytest-baseline-clean.ESi619lW/command.txt
readback: task1/baseline-summary.json
```

GATE-002 result: VALID. `task1/baseline-summary.json` records readback; `scratch/pytest-baseline-clean.ESi619lW/junit.xml` contains 146 testcases with zero failures/errors/skips. Controller and gw0 through gw7 each have a distinct JSON proof identifying the exact project Python and the same registered run/tmp. No source modules moved and no product configuration changed.

## CP-002: Task 1 baseline checkpoint

```yaml
checkpoint_id: CP-002
last_valid_experiment: GATE-002
current_hypothesis: NONE
working_tree_status: clean at Task 1 checkpoint; exact commit and readback in evidence task1-report.json
owned_processes: NONE
preserved_processes: all pre-existing processes recorded in task1/preflight.json
confirmed_conclusions:
  - approved documents and ignored worktree established on main a137842
  - pytest 9.2.0 and xdist 3.8.0 installed only in the stable project environment
  - every pre-existing package version is identical before/after provisioning; runtime environments read-only
  - all original tests pass with required parallelism and tempfile proofs
  - Python voice help/defaults are inert under denied runtime imports/actions
  - no ROS/live/visual acceptance required for this source-only checkpoint
open_risks:
  - future pytest commands must remove inherited ROS overlay variables in subprocesses
  - Task 2 through Task 5 remain unexecuted; runtime installation/provenance is not yet established
next_command: cd /home/matianyi/Projects/so101_test/.worktrees/repo-organisation && cat docs/superpowers/plans/2026-10-29-so101-test-organisation-plan.md
```

Inline self review: spec compliance PASS and Task 1 quality PASS. Reviewed the staged scope against each Task 1 item, original approval hashes, unchanged module/config/lockfile contents and preserved root import fixture. Evidence instrumentation opts in only with `SO101_TEST_EVIDENCE_RUN_DIR`, checks all three tempfile variables plus the interpreter's actual directory, and records separate controller/worker files without private environment values. Opt-out/mismatch/proof checks passed. The baseline failure was an environment/plugin boundary, retained as INVALID; application behaviour was not repaired. Native-worktree fallback follows the explicit approved placement and coordinator ruling. No independent reviewer, hardware run, remote push or Task 2 execution occurred.

Final retention classification for Task 1:

- Retained: all original evidence plus `task1/`, both baseline run directories and their logs/results/proofs; external helper paths and SHA256 values are in `task1/helpers.json`, interpreter/uv/rollout paths and hashes in `task1/external-executables.json`. No builds or wheels were produced.
- Archived: NONE.
- Deletion candidates after readback: `scratch/pytest-baseline.YvUPD9KY/tmp`, `scratch/pytest-baseline-clean.ESi619lW/tmp`, and `task1/hook-verification/tmp`. Retain logs, JUnit, results and proof JSON. Nothing was deleted.

Task 1: complete (main approval/ignore commit a137842; branch checkpoint SHA in task1-report.json; inline spec and quality review clean). Hand off sequentially to a fresh approved GPT-6.1 Sol / High Task 2 executor.


## GATE-003: Task 2 configuration and launcher contracts

```yaml
status: VALID
prior_experiment: GATE-002
hypothesis: legacy file reads and unconditional Bash assignments overwrite explicit process configuration
prediction: legacy consumers fail process override assertions; shared loaders preserve set and empty values
single_variable: explicit config loader, unchanged config moves, shell anchoring and delegates
lifecycle: N/A (isolated headless subprocess tests; no robot stack)
preconditions:
  - Task 1 exact project Python, unchanged runtime environments and original baseline
  - fake executables intercept Python, uv, viewer/network and device utility boundaries
success_criteria:
  - functional assertion RED then GREEN; full tests/ on eight workers; bash syntax checks
invalid_criteria:
  - collection/setup failure, real external utility access or scratch/provenance failure
provenance:
  source_commit: 5d624cd plus Task 2 changes; exact checkpoint in task2-report.json
  install_overlay: editable project source from approved worktree; no ROS environment
  runtime_executable: /home/matianyi/Projects/so101_test/.venv/bin/python
  ros_domain_id: N/A
  gz_partition: N/A
commands:
  - scratch/pytest-task2-red-clean.3n0ui7bm/command.json; exit 1
  - scratch/pytest-task2-green-clean.fpsfwnzu/command.json; exit 0
  - scratch/pytest-task2-final.wi5uoxqe/command.json; exit 0
observed:
  - canonical RED has eight assertion failures, zero errors/skips, including every launcher overwriting FOLLOWER_PORT
  - focused GREEN has 21 passed, zero failures/errors/skips
  - final full tests/ has 167 passed, zero failures/errors/skips, eight workers on CPU32, elapsed 1.542 seconds
  - controller and gw0 through gw7 prove identical NVMe tempfile placement in fresh run/tmp
  - 15 Bash files pass bash -n; config bytes, pyproject, uv.lock and Python version file unchanged
  - project editable wheel built by uv 0.12.17; no application dependencies changed
inferred:
  - approved config precedence correction is isolated from robot/action/model behavior
conclusion: Task 2 contracts pass; package moves and runtime deployment remain for later tasks
evidence:
  - task2/gate-readback.json
  - task2/compatibility-provenance.json
  - task2/bash-syntax.json
  - task2/inline-self-review.json
decision: KEEP
next_experiment: Task 3 voice migration
```

Initial `pytest-task2-red.k7bv8_uk` is mixed fixture-invalid: record/rollout temporary replacement prefixes contained spaces in an unquoted legacy assignment. It is retained and excluded from canonical RED. Correcting only the fake executable directory name established the eight valid override failures above. Initial `pytest-task2-green.hiba2n1w` had 18 pass and two incorrect test expectations for relative Python paths; the plan requires absolute sibling calls, so those expectations were corrected. No product behavior was changed to accommodate either fixture issue. All run commands, actual exit codes, elapsed times and counts are in `task2/gate-readback.json`.

## CP-003: Task 2 configuration and shell checkpoint

```yaml
checkpoint_id: CP-003
last_valid_experiment: GATE-003
current_hypothesis: NONE
working_tree_status: clean at Task 2 checkpoint; exact SHA in task2-report.json
owned_processes: NONE
preserved_processes: all existing host processes; no services started
confirmed_conclusions:
  - Python config selection and literal parsing preserve declared process overrides including empty values
  - seven root wrappers delegate quoted argv and exit 23; shell bodies anchor repository root from outside cwd
  - Bash defaults retain source expansion and SSH viewer fallback while preserving explicit values
  - all 167 tests pass with required parallelism; 15 Bash syntax checks pass
  - arms.env and camera.env moved byte-for-byte; runtime real/voice environments untouched
open_risks:
  - project environment currently points editable at approved worktree; Task 5 must rebind stable checkout
  - Task 3 must migrate test_config.py legacy voice_policy import alongside canonical voice test imports
  - Task 3/4 must replace owning flat shell Python paths with package -m calls and adapt launcher expectations
next_command: read Task 3 plan; grant next fresh executor sequential source/ledger/environment lease
```

Inline self review: spec PASS and quality PASS; details in `task2/inline-self-review.json`. No independent reviewer was dispatched. Runtime, ROS, hardware and visual acceptance are N/A for this source-only task.

Retention for Task 2: retained all `task2/`, `task2-turn-recovery.json` and every `scratch/pytest-task2-*` run, logs, JUnit and process proofs. Archived: NONE. Deletion candidates after readback: each Task 2 run's `tmp/` subtree. Nothing was deleted. External editable wheel/build cache and executable helper remain at their approved build/tools paths with path, SHA256 and reproduction command in `task2/compatibility-provenance.json`.
