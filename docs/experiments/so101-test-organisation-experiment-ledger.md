# so101_test organisation experiment ledger

```yaml
task_id: so101-test-organisation-20261029-e8a252c0
goal: organise the application in its existing src package without robot behaviour changes
success_contract: approved migration; baseline and final full tests with min(8, CPU) workers; installed provenance in three environments
worktree: /home/matianyi/Projects/so101_test/.worktrees/repo-organisation
branch: chore/so101-test-organisation
base_commit: c724e389536e56875a54642b230d48532dfbde35
current_commit: Task 5 final integrated checkpoint; exact SHA recorded in evidence task5-report.json
evidence_root: /data/work/so101-evidence/repo-organisation/20261029-e8a252c0
confirmed_conclusions:
  - approval document hashes match execution-approval.json (CP-001)
  - original main was clean except approved planning documents (CP-001)
  - all 146 original tests pass with eight workers after removing inherited ROS overlay variables in the test subprocess (GATE-002)
  - existing application dependencies are unchanged in all three environments (CP-002)
  - explicit config and launcher contracts pass; all 167 tests pass with eight workers (GATE-003)
  - canonical voice identity, guarded help and launcher contracts pass; all 186 ordinary tests pass with eight workers (GATE-004)
  - connected camera/operations import and CLI contracts pass; all 237 ordinary tests pass with eight workers (GATE-005)
  - complete wheel deployed into managed runtimes with exact file-byte provenance and unchanged application versions; all 241 tests pass with eight workers (GATE-006)
  - original main integrated locally and project editable rebound to stable checkout; stable full gate passes 241 tests, zero skips (CP-007)
disproven_routes:
  - running this non-ROS gate with inherited ROS PYTHONPATH is invalid (GATE-001)
open_hypotheses:
  - NONE
latest_checkpoint: CP-007
next_experiment: NONE
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


## GATE-004: Task 3 voice package and entry boundaries

```yaml
status: VALID
initial_status: PLANNED
prior_experiment: GATE-003
hypothesis: canonical voice module identity and installed module entry paths are absent before the voice move
prediction: consumer assertions fail before migration and pass after relative-import moves and narrow delegates
single_variable: voice source ownership, imports, root delegates and shell module dispatch
lifecycle: N/A (isolated headless tests; no robot stack)
preconditions:
  - clean Task 2 checkpoint 2147056436007b29e3f19e6d7ccfb2a775cc1572 and exclusive Task 3 write lease
  - exact project Python editable at the approved worktree; real and voice environments read-only
  - import/action guards deny policy, hardware, ASR, API and model reads during help
success_criteria:
  - functional assertion RED then focused GREEN; existing cancellation tests retained
  - full tests/ on min(8, CPU) workers with JUnit and per-process tempfile proof
invalid_criteria:
  - collection/setup failure, real runtime access or scratch/provenance failure
provenance:
  source_commit: 2147056436007b29e3f19e6d7ccfb2a775cc1572 plus Task 3 changes
  install_overlay: editable project at approved worktree; ROS variables removed
  runtime_executable: /home/matianyi/Projects/so101_test/.venv/bin/python
  ros_domain_id: N/A
  gz_partition: N/A
commands:
  - scratch/pytest-task3-red-boundary.wmnz243e/command.json; exit 1
  - scratch/pytest-task3-green.irp8lqqs/command.json; exit 0
  - scratch/pytest-task3-full.k2hvywm9/command.json; exit 0
observed:
  - canonical RED has seven intended assertion failures, zero errors/skips; identity package absence and six wrong flat launcher argv cases
  - focused GREEN has 186 passed, zero failures/errors/skips, including all five original voice test modules
  - full tests/ has 186 passed, zero failures/errors/skips; xdist8 CPU32; elapsed 1.613 seconds
  - all nine controller/worker proofs use exact project Python and fresh registered run/tmp
  - guarded help passes 12 agent/latency module/stub and absent/empty/missing-config combinations with zero forbidden actions
  - Task 1 parser defaults/actions and normalized agent help match; four actual project-Python module/root help calls outside cwd exit zero
  - nine source module ASTs and five original voice test module ASTs unchanged except permitted imports
  - voice Bash syntax and git diff --check pass; 22 config/helper/metadata/Task4 paths byte-identical
conclusion: Task 3 voice migration passes; runtime wheel deployment and connected source moves remain for Task 4/5
decision: KEEP
next_experiment: Task 4 connected camera/operations migration
```

Task 3 execution uses the approved shared evidence ledger and registered tools/build paths. The generic execution-skill scratch ledger and task scripts are replaced by this plan's explicit evidence/scratch contract; no second workspace or reviewer is created. Only Task 3 is authorised in this lease.


Initial `scratch/pytest-task3-red.y07zw0bw` is retained as pre-migration entry diagnosis: 18 failed and eight passed, no collection errors or skips. Its missing canonical help imports are not used as source RED. The narrower canonical RED above executes seven direct consumer assertions, proving the absent canonical identity and legacy launcher argv boundary without import/collection failures. All four Task 3 runs have commands, actual exit codes, elapsed time, JUnit counts/hashes and scratch proofs in `task3/gate-readback.json`.

## CP-004: Task 3 voice package checkpoint

```yaml
checkpoint_id: CP-004
last_valid_experiment: GATE-004
current_hypothesis: NONE
working_tree_status: clean at Task 3 checkpoint; exact SHA in task3-report.json
owned_processes: NONE
preserved_processes: all existing host processes; no services started
confirmed_conclusions:
  - all nine voice implementations live only under src/so101_test/voice with relative eager/delayed imports
  - canonical say monkeypatch affects handle_text; all existing stop/home/quit and in-flight/retry cancellation assertions remain unchanged
  - two narrow root Python delegates retain config defaults/overrides, guarded main and installed package identity
  - voice launcher retains interpreter default/override, root cwd, config, argv, caches, ROS cleanup and help/fake camera-lock bypass
  - conftest root sys.path insertion removed; opt-in tempfile evidence hook retained
  - parser/help baseline and source behavior comparison pass; all 186 ordinary tests pass on eight workers
open_risks:
  - real/voice environments do not yet contain the package wheel; managed runtime execution waits for Task 5 deployment
  - project environment remains editable at the worktree; Task 5 must rebind stable checkout after integration
  - Task 4 flat camera/operations paths and launchers intentionally remain at the Task 2 checkpoint
next_command: read Task 4 plan and task3-report.json; wait for explicit next exclusive lease
```

Inline self review: spec PASS and quality PASS; details in `task3/inline-self-review.json`, source/CLI evidence in `task3/compatibility-provenance.json`, installed project origins in `task3/installed-origins.json`. No independent reviewer was dispatched. No ACT, language fallback, visual retry, runner, ASR timing, model defaults or external artifact paths changed. Runtime, ROS, hardware and visual acceptance are N/A for this source-only task.

Retention for Task 3: retain `task3-preparation.json`, `task3/` and all four `scratch/pytest-task3-*` runs with logs, JUnit and proof files. Archived: NONE. Deletion candidates after readback: each of those four runs' `tmp/` subtree. Nothing was deleted. Two external read-only helpers remain in `/data/work/so101-tools/repo-organisation-task3/`, with paths and SHA256 in `task3/helpers.json`. No builds or wheels were produced in Task 3.

Task 3: complete; exact checkpoint commit in `task3-report.json`. Release source/ledger/project-environment ownership after final clean readback and report. Do not start Task 4 in this lease.


## GATE-005: Task 4 connected camera/operations migration

```yaml
status: PLANNED
prior_experiment: GATE-004
hypothesis: legacy diagnostics execute SDK/config/device operations on import and launchers still target flat scripts
prediction: isolated import and launcher consumer assertions fail before migration, then pass with guarded canonical entry points
single_variable: connected camera/operations ownership, entry boundaries and owning shell module dispatch
lifecycle: N/A (isolated headless stub subprocesses; no robot stack)
preconditions:
  - exclusive Task 4 source/ledger/project-environment lease after clean CP-004 07fcc751
  - exact stable project Python editable at approved worktree; real/voice environments untouched
  - external SDK, OpenCV, LeRobot and config/cache/device boundaries stubbed or denied
success_criteria:
  - assertion RED then focused GREEN; full tests/ with min(8, CPU) and fresh NVMe scratch/JUnit/proofs
  - source AST parity except approved imports/main extraction/guard relocation; Bash syntax clean
invalid_criteria:
  - collection/setup failure or actual device, camera, ASR, model, API or runtime-environment access
provenance:
  source_commit: 07fcc751f449e1f1ad8b22dcba034916f1d70efa plus Task 4 changes
  runtime_executable: /home/matianyi/Projects/so101_test/.venv/bin/python
  install_overlay: editable project at approved worktree; ROS variables removed
  ros_domain_id: N/A
  gz_partition: N/A
```

Ruling: this approved shared evidence ledger and scratch replace the generic execution skill's extra workspace scripts; only Task 4 is leased. Existing calibration argument guards must move into their existing main functions so delegates retain usage and exit behavior. No extra permission, reviewer, runtime install or second evidence root is required.


GATE-005 final status: VALID. Canonical boundary RED in `scratch/pytest-task4-red-boundary.6htrce77` has five actual consumer assertion failures (two eager SDK imports and three flat launcher argv), zero collection errors/skips, exit 1. Expanded pre-migration RED `scratch/pytest-task4-red-all.vtzo8ras` has 50 failures and 36 passes, zero errors/skips; canonical target checks fail before unsafe legacy execution. The first GREEN and focused root-argv diagnosis are fixture-invalid: `runpy.run_path` correctly exposes the executed absolute script path as `argv[0]`, while the test expected a basename. Corrected only that expectation; production unchanged. Both diagnostic runs are retained and excluded from source RED.

Focused clean GREEN: `scratch/pytest-task4-green-clean.kswj8mn0`, exit 0, 88 passed, zero failed/errors/skipped, elapsed 2.980 s. Full ordinary gate: `scratch/pytest-task4-full.78x_3vrw`, exit 0, 237 collected/executed/passed, zero failed/errors/skipped, xdist8/CPU32, elapsed 1.843 s (JUnit 1.653 s). All nine controller/gw0–gw7 proofs identify the exact project Python and fresh registered run/tmp; every recorded gate process has ended. Commands, times, counts, hashes and proof readback: `task4/gate-readback.json`.

Read-only compatibility verification proves all nine moved modules retain executable AST except approved relative imports/main extraction/validation relocation, removed unused capture HERE, and canonical alignment chdir removal. Existing calibration usage exits are inside their existing main signatures; their root delegates preserve guard behavior. Twenty-eight config/helper/metadata/voice/other-launcher paths remain byte-identical. Only three owning shell Python invocation lines change; existing calibration `lerobot-calibrate`, rollout `lerobot-rollout`, uv no-sync and runtime choices remain. Fifteen Bash syntax checks and git diff --check pass. Evidence: `task4/compatibility-provenance.json`, `task4/bash-syntax.json`.

## CP-005: Task 4 connected camera/operations checkpoint

```yaml
checkpoint_id: CP-005
last_valid_experiment: GATE-005
current_hypothesis: NONE
working_tree_status: clean at Task 4 checkpoint; exact SHA in task4-report.json
owned_processes: NONE
preserved_processes: all existing host processes; no services started
confirmed_conclusions:
  - five camera and four operations implementations live only in their canonical package groups
  - diagnostics import without SDK/config/cache/device activity and preserve controlled-main behavior
  - adapter patches install in original order, capture originals once and precede external main
  - record -> canonical align_side -> canonical calib_capture identity remains intact
  - all nine remaining Python delegates preserve argv/exit/config and declared cwd behavior
  - three affected shell bodies dispatch canonical modules through their existing interpreter choices
  - 237 ordinary tests pass on eight workers with zero skips/failures/errors; source AST parity passes
open_risks:
  - real/voice wheel deployment remains Task 5 and must wait for separate mic task managed-environment release
  - project editable remains at worktree; Task 5 must rebind stable checkout after local integration
  - physical/visual/live runtime acceptance N/A for this source-only scope
next_command: coordinator grants Task 5 only after runtime environment lease is released
```

Inline self review: spec PASS and quality PASS; `task4/inline-self-review.json` records source/order/cwd/import review and mutation reasoning. No independent reviewer or extra agent was dispatched. No model/ACT/motion/ASR/camera parameter or artifact-default changes occurred. No project reinstall, managed runtime write, hardware/GUI, network/API, ROS, benchmark, integration or remote push occurred.

Retention for Task 4: retain `task4/` and all six `scratch/pytest-task4-*` runs, with logs/JUnit/results/proofs. Archived: NONE. Deletion candidates after readback: each of the six run/tmp subtrees; no deletion is authorised or performed. Two external helpers remain in `/data/work/so101-tools/repo-organisation-task4/`, with path/SHA256 in `task4/helpers.json`. No builds or wheels were produced.

Task 4: complete; exact checkpoint in `task4-report.json`. Release source/ledger/project-environment ownership after final clean readback. Do not start Task 5 under this lease.

## GATE-006: Task 5 installed distribution and stable checkout

```yaml
status: PLANNED
prior_experiment: GATE-005
hypothesis: explicit outside-cwd provenance detects an incorrect interpreter, package origin or editable source; the complete package distributes without checkout configuration
prediction: negative controls expose missing validation assertions, then reject all three incorrect paths; real/voice wheel readback covers all application modules
single_variable: distribution/provenance validation, documentation paths and final project deployment
lifecycle: N/A (headless source and installed-code checks; no robot stack)
preconditions:
  - Task 5 exclusive source/ledger/project-environment lease at clean 49d5eb8c8debe61fc90868cecff20ce0ac0f8dbe
  - managed real/voice installation waits for the coordinator's separate runtime lease
  - exact stable project Python; fresh NVMe scratch and sanitized ROS variables for each pytest run
success_criteria:
  - validator assertion RED then GREEN; complete ordinary tests/ at min(8, CPU), nine tempfile proofs, zero added skips
  - verified complete wheel, project-only runtime installs, unchanged application dependency versions
  - clean local fast-forward and editable rebind to stable original checkout; exact outside-cwd origins
invalid_criteria:
  - collection/setup failure, unintended dependency changes, unsafe runtime access or provenance/scratch mismatch
provenance:
  source_commit: 49d5eb8c8debe61fc90868cecff20ce0ac0f8dbe plus Task 5 changes
  runtime_executable: /home/matianyi/Projects/so101_test/.venv/bin/python
  install_overlay: editable at approved worktree until local integration; no ROS overlays
  ros_domain_id: N/A
  gz_partition: N/A
```

Ruling: the application package already exists after Tasks 2–4, so Task 5 RED tests the new provenance validator's consumer contract with wrong interpreter/package/editable-source arguments, before adding its assertions. Missing runtime installation is setup, never source RED. Use the existing registered ledger/evidence layout and inline self review; the approved plan overrides generic skill workspace/deletion/reviewer instructions.


GATE-006 status: RUNNING; source validation complete, managed runtime deployment and integration pending. Provenance validator RED `scratch/pytest-task5-red-provenance.11xyil2c`: three assertion failures accepting wrong interpreter/package/editable-source arguments, one positive pass, no collection errors/skips, exit 1. The first GREEN had one fixture issue: the wrong package path was inside cwd, so the outside-cwd precondition correctly failed before the intended origin check. This is retained as fixture-invalid; moving only that fake path to a sibling yields clean GREEN `scratch/pytest-task5-green-provenance-clean.plfohuxj`, four passed, exit 0.

Final full ordinary gate `scratch/pytest-task5-full.9vkej8jr`: 241 collected/executed/passed, zero failures/errors/skips, xdist8/CPU32, exit 0, elapsed 1.891 s. All nine exact-Python controller/worker tempfile proofs read back correctly, and gate processes ended. Baseline was 146 tests with zero skips; Task 4 had 237 tests with zero skips. New tests account for four additional cases in Task 5. Readback: `task5/gate-readback.json`.

The offline bundled uv_build/uv 0.12.17 build produced `/data/work/so101-build/repo-organisation/20261029-e8a252c0/wheels/final/so101_test-0.1.0-py3-none-any.whl`, SHA256 `8e7d0e78682e699f664753a6e4017c995cdfe72ea6251bc935318232b18a425f`. All 18 application modules, config helper and four inert/root init files match source bytes; only package files and distribution metadata occur in the wheel. No checkout configuration, root compatibility files or external artifacts are included. Build commands, metadata and manifest: `task5/wheel.json`. The first successful wheel is retained with `task5/wheel-initial.json`; README source literals were restored before the final build. An initial verifier incorrectly counted ZIP directory records as files; this verifier-only issue was corrected and the same first wheel inspected without rebuilding, recorded in `task5/wheel-first-verifier-diagnosis.json`.

README prose is English and reviewed with the project humanizer skill. Original hardware facts, identifiers, cache paths, commands and placeholders remain, with intended config/doc and no-sync command changes. The teaching HTML and historical voice plan move byte-identically. Local Markdown links and HTML anchors/assets resolve. Seventy-two source/default/doc paths, all 15 Bash syntax checks, unchanged application/metadata/lock/greeting bytes and the exact root delegate inventory pass: `task5/compatibility-provenance.json`. Project provenance outside cwd passes at the worktree; application dependency versions are unchanged. Inline source review: `task5/inline-self-review.json`.

Managed runtime installation is waiting only for the coordinator's separate lease. No managed runtime project install, hardware/camera/ASR/model/API/ROS/GUI operation, commit/integration, remote push or deletion has occurred in Task 5 so far. Original main remained clean at approved `a1378429a39ef014befdab36ee8779809c0a2b06`. External task helpers and hashes are in `task5/helpers.json`. Retain both wheels/build logs and all four Task 5 pytest runs; archived NONE; each run/tmp is a deletion candidate after readback, with no deletion authorised.


GATE-006 final status: VALID. Master explicitly granted the managed real+voice install lease after mic Phase 1 released its read lease; `task5/runtime-preinstall-preflight.json` found no active runtime or unreadable same-user processes. Both `uv pip install --offline --python <exact-python> --no-deps <exact-final-wheel>` commands exited 0. Only `so101-test==0.1.0` was added; all 101 real and 114 voice nonproject distribution versions remain identical. Exact outside-cwd interpreter/module paths, wheel source URL, independently measured SHA256, distribution file coverage and all 23 installed package files' bytes match the verified wheel. `uv` does not store a local-wheel archive hash in `direct_url.json`; the initial metadata-only hash assumption is retained as verifier-invalid, and actual artifact hashing plus every installed file's bytes provide the required proof. No reinstall or dependency repair was needed. Evidence: `task5/dependency-invariance-after.json`, `task5/{real,voice}-deployed-provenance.json`, `task5/runtime-wheel-verifier-diagnosis.json`.

Guarded help through the root shell and root Python entry uses the exact managed voice interpreter and its wheel implementation. Complete help text (except invocation path), parser defaults/actions and both runtime greeting commands match the Task 1 baseline. Hardware/device/config/cache/model/ASR/network actions are denied; zero forbidden attempts occurred. `task5/managed-runtime-readback.json` records the readbacks. The managed runtime window was explicitly RELEASED to the coordinator immediately afterward; no further managed environment writes or reads are part of the remaining project-only integration.

After correcting the optional-hash verifier assumption, focused provenance passes 4/4 in `scratch/pytest-task5-final-provenance.z6mn_dj_`. Full `tests/` passes 241/241, zero failures/errors/skips, xdist8/CPU32, nine tempfile proofs, exit 0 and elapsed 1.772 s in `scratch/pytest-task5-final-full.212abthq`. All gate processes ended. Source/default/doc/link/syntax/readback audit passes again. `task5/inline-self-review.json` records PASS for spec and quality, with no critical/important/minor findings. Generic skill independent-reviewer/menu/deletion flows are replaced by the user's explicit inline-review, approved local-fast-forward and retention instructions.

## CP-006: Task 5 distribution and source checkpoint

```yaml
checkpoint_id: CP-006
last_valid_experiment: GATE-006
current_hypothesis: NONE
working_tree_status: final Task 5 source/docs checkpoint; exact SHA in task5-report.json
owned_processes: NONE
preserved_processes: all unrelated host processes; managed runtime lease released to Master
confirmed_conclusions:
  - 18 application modules plus config helper distribute with exact source bytes and no checkout configuration or root delegates
  - real/voice wheel installations have exact outside-cwd provenance and unchanged nonproject versions
  - guarded managed voice help/parser/actions match baseline without hardware/model/ASR/network activity
  - README English rewrite and exact-byte historical document moves preserve facts and resolve local links
  - 241 complete ordinary tests pass at eight workers with zero skips/errors/failures
open_risks:
  - project editable still points to task worktree until the approved stable-checkout rebind
  - local main integration must stop on user changes/divergence; never stash/reset/force
  - physical/visual/runtime action acceptance is N/A for this source-only migration
next_command: recheck original clean main at a137842; local git merge --ff-only chore/so101-test-organisation
```

Retention at CP-006: retain all six Task 5 pytest runs, both wheel versions, build/install/help/provenance logs and all JSON readbacks. Archived NONE. All six run/tmp subtrees are deletion candidates after readback; nothing was deleted. External helpers/build files are recorded by path, bytes and SHA256 in `task5/external-artifact-manifest.json`; exact build/install commands reproduce the wheel/deployment. Source and ledger lease remain with Task 5 through local integration and stable rebind.


## CP-007: final stable checkout and ownership release

The original checkout was clean on `main` at exact approved bootstrap `a1378429a39ef014befdab36ee8779809c0a2b06`; the commit object exists, and it is an ancestor of the task branch. The local `git merge --ff-only chore/so101-test-organisation` integrated source checkpoint `b7404c8c9fa3f0d44d3c1ab6a49d0e392f4cf0ff` without a remote operation. Records: `task5/integration-preflight.json`, `task5/local-fast-forward.json` and its log.

The exact stable project Python was rebound with `uv pip install --offline --python /home/matianyi/Projects/so101_test/.venv/bin/python --no-deps -e /home/matianyi/Projects/so101_test`. Outside-cwd imports now resolve to that stable checkout, and editable `direct_url.json` points there. All 76 nonproject distributions in the sanitized project environment retain their versions. Real/voice origins remain the independently verified wheel locations from the released managed install window, with no editable worktree pointers. Their package bytes and metadata do not depend on checkout integration. Evidence: `task5/project-stable-rebind-command.json`, `task5/project-stable-provenance.json`, `task5/dependency-invariance-stable.json`, and retained runtime deployed provenance.

Postintegration full gate from the stable checkout: `scratch/pytest-task5-stable-full.bsiknktc`, 241 collected/executed/passed, zero failed/errors/skipped, xdist8/CPU32, exit 0, elapsed 1.961 s (pytest 1.76 s), nine exact-Python controller/worker proofs under fresh run/tmp; all gate processes ended. This full suite includes launcher stubs and denied-runtime root/module help at stable paths. Additional guarded root shell/Python voice help and parser/default/action comparisons use only the project interpreter after the managed window was released. `uv run --no-sync so101-test` prints its original greeting; both metadata and lock hashes remain unchanged. All 14 shell delegates/bodies are executable. Evidence: `task5/stable-public-commands.json` and `task5/{stable-shell,stable-root}-voice-safety.json`.

Final source/default/rename/link inventory, 15 Bash syntax checks, seven gate readbacks and inline self review pass. The final documentation-only completion commit updates this ledger and plan checkboxes; application/test/README bytes remain identical to the stable full-gate source checkpoint. Main is fast-forwarded once more to include that checkpoint, with expected-head and cleanliness checks again. Exact final commits and status are in `task5-report.json`. No source fix, package rebuild, further runtime environment access or repeated full gate is needed for this ledger-only finish.

```yaml
checkpoint_id: CP-007
last_valid_experiment: GATE-006 plus stable-checkout full readback
current_hypothesis: NONE
working_tree_status: clean original main and task branch at final integrated commit; exact SHA in task5-report.json
owned_processes: NONE
preserved_processes: all unrelated host processes; mic work may proceed under Master ownership
confirmed_conclusions:
  - all approved source grouping/config/delegate/entry/provenance contracts pass
  - project environment points to stable original checkout; real/voice use exact verified wheel
  - no application dependency versions, model/device defaults, artifact paths or lock resolution changed
  - 241 ordinary tests pass from stable checkout with eight workers and zero skipped/failed/errors
  - public greeting, root help and stubbed launcher commands work at stable paths
open_risks:
  - physical robot, camera, ASR, model/API and GUI acceptance remain N/A and are not claimed
next_command: NONE; Task 5 complete; all leases released after clean report
```

Final retention: retain the registered root, all seven Task 5 pytest runs (including RED and fixture-invalid records), runtime/source/integration evidence, both wheel versions and the local worktree. Archived NONE. Each Task 5 run/tmp and previously classified scratch remains a deletion candidate after readback; no evidence/build/worktree deletion occurred. Every external helper/build file has path, size and SHA256 in `task5/external-artifact-manifest.json`; build/install/rebind commands are retained. Inline self review is PASS, with no critical/important issues or deferred minor findings. Rulings were limited to the explicit approved workflow and verifier boundary corrections; no robot behavior was changed.

Task 5: complete. Release source/ledger/project-environment ownership after final clean readback; managed real+voice install ownership was already released before local integration. No push or cleanup is authorised or performed.
