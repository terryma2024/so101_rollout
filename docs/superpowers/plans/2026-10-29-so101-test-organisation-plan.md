# so101_test source organisation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Preserve the user's chosen method: new GPT-6.1 Sol / High execution subagents with inline self review; no independent reviewer or `dst`.

**Goal:** Put the application in its existing src package while preserving public commands, runtime identities and robot behaviour.

**Architecture:** Move modules into shallow voice, camera and operations groups. Keep narrow root delegates and explicit external configuration. Test installed code, and deploy only the local project to the existing interpreter environments.

**Tech Stack:** Python >=3.12, existing uv/uv_build and LeRobot 0.6.1 environments, Bash, pytest and pytest-xdist.

**Spec:** [2026-10-29-so101-test-organisation-design.md](../specs/2026-10-29-so101-test-organisation-design.md)

## Global Constraints

- Explicit user confirmation of both documents precedes implementation, worktree creation, installations and tests.
- Work on ai-station directly; do not SSH to ai-station. Read the SO-101 skill and applicable repository instructions before execution.
- Use the source mapping and exact public entry-point list in the spec. Preserve filenames, arguments, positional semantics, output and exit codes, except the specified config precedence correction.
- Preserve ACT horizons, policy/model parameters, stop/cancel behaviour, device IDs, camera settings, calibration/cache identity and all external artifact paths.
- Do not upgrade application dependencies. Runtime installs are local-project-only with `--no-deps`; provision only missing test tools and the constrained build backend described in the spec.
- Evidence root: `/data/work/so101-evidence/repo-organisation/20261029-e8a252c0`. No evidence outside it, no external symlinks inside it, no evidence deletion.
- Build/wheel root: `/data/work/so101-build/repo-organisation/20261029-e8a252c0/`. Register outputs by path, SHA256 and reproduction command.
- Every full ordinary gate collects all `tests/` with xdist `min(8, CPU)`. Each pytest run uses fresh registered scratch and exact-interpreter tempfile proof.
- No broad ROS gates, benchmarks, hardware/camera/ASR access, network/API calls, policy-loading integrations or remote push.
- Use one ledger writer and sequential task handoffs. Every Sol executor performs inline self review; do not dispatch a reviewer.

## Review Focus

- Invocations from another cwd or paths containing spaces must still select the correct root, config and installed implementation. Task 2 owns launcher assertions; Task 5 owns installed provenance.
- Already-set values, including empty values and viewer defaults derived from `SSH_CONNECTION`, must survive config loading. Task 2 owns the Bash/Python boundary checks.
- `voice_agent.say` monkeypatches must affect the implementation, and stop/cancel must invalidate in-flight work. Task 3 owns canonical identity and the existing cancellation suite.
- Diagnostic imports without SDKs or config must stay inert, while recording patches still precede LeRobot main exactly once. Task 4 owns isolated subprocess checks.
- Runtime environments must not retain an editable pointer into the temporary worktree. Task 5 owns wheel provenance and stable-checkout rebind checks.

## File responsibilities and interfaces

Use the spec's grouped mapping as the move list; do not rename modules within groups. New files are `src/so101_test/config.py`, three inert group `__init__.py` files, `scripts/lib/common.sh`, the eleven root Python stubs, seven replacement shell stubs, four focused test modules, and one task ledger. The four new test modules are `tests/test_config.py`, `tests/test_launchers.py`, `tests/test_entry_boundaries.py` and `tests/test_package_provenance.py`.

- `resolve_config_dir(explicit: str | pathlib.Path | None = None) -> pathlib.Path`: explicit directory, environment directory, cwd/config; selected missing paths fail.
- `read_env_file(path: str | pathlib.Path) -> dict[str, str]`: legacy literal splitting with no shell evaluation.
- `load_arms_env(path: str | pathlib.Path | None = None) -> dict[str, str]`: selected arms file plus process overrides for its keys.
- `voice_policy.read_arms_env(path=None)`: unchanged caller interface delegating to the loader.
- `so101_init`: fixed-location Bash root anchor, root cwd and absolute exported config directory.
- `so101_source_defaults FILE`: Bash-source trusted defaults, restore pre-existing keys and export effective values.
- New guarded `main() -> None`: camera capture, two diagnostics and two visualization adapters. Existing main signatures remain unchanged.

### Task 1: Establish an approved isolated baseline

Files: modify `.gitignore` and add evidence-only worker instrumentation to `tests/conftest.py`; commit the two approved planning documents; create `docs/experiments/so101-test-organisation-experiment-ledger.md` in the implementation worktree. Evidence: environment, baseline and checkpoint records in the registered root.

Consumes: explicit approval, clean baseline commit and registered root. Produces: ignored worktree, baseline gate and exact `TEST_PYTHON`, `UV_BIN`, `WORKTREE`, `BUILD_ROOT` paths recorded for later tasks.

- [x] Record approval, hostname, pwd, commit/branch/status, worktree/submodule inventory, relevant process names and tmux state. Do not inspect private environment values or start stacks. ROS/GUI are N/A for this LeRobot source task.
- [x] Read the worktree skill. Confirm no native worktree mechanism is available before Git fallback. Add `.worktrees/` to `.gitignore`, commit only that and the approved documents on original `main`, verify `git check-ignore .worktrees/`, then create `.worktrees/repo-organisation` on `chore/so101-test-organisation`. Do not recreate an existing worktree or branch blindly.
- [x] Register the same evidence root in the ledger. Record the preflight checkpoint; tests are planned gates, not robot experiments. Use N/A for ROS domain, Gazebo partition and live outcomes, with the source-only reason.
- [x] Resolve `uv` and verify exact executables: stable `.venv/bin/python`, real and voice `bin/python`, real `bin/lerobot-rollout`. Verify Python versions, test dependency origins, CPU/memory/load and application dependency snapshots. `TEST_PYTHON` is `/home/matianyi/Projects/so101_test/.venv/bin/python`; do not substitute another interpreter silently.
- [x] If needed, provision only the spec's missing pytest/xdist tooling in that project environment, recording resolver plan and actual versions first. Reject any proposed upgrade/removal of an existing application dependency. Provision the existing constrained build backend in build isolation only. Missing closure blocks the gate; never call it source RED or run serial as a replacement.
- [x] Add `pytest_sessionstart(session) -> None` instrumentation to conftest that verifies each controller/worker tempfile directory against exported TMPDIR and writes a unique proof under its run directory. Keep the existing root import setup for this baseline. Run baseline full `tests/` in the worktree using the gate recipe below, before moving modules. Save safe voice `--help`, parser defaults and source CLI/patch/config inventory. Use text/AST for hardware launchers, not execution.
- [x] Read back JUnit, skips and exit status. If baseline fails, report its exact boundary before proceeding; do not silently repair unrelated behaviour. Commit ledger registration after recording the baseline checkpoint.

### Task 2: Make config and shell locations explicit

Files: move `arms.env`, `camera.env` to `config/`; create `src/so101_test/config.py`, `scripts/lib/common.sh`, `tests/test_config.py`, `tests/test_launchers.py`; move all seven shell bodies to `scripts/`; replace root shell files with delegates. Modify the four Python config readers in their current locations initially. Task 3/4 then move them.

Consumes: Task 1 environment and baseline. Produces: loader interfaces above and root wrappers that use existing flat Python paths until their owning migration task switches each invocation.

- [x] Add `test_config_selection_and_missing_path`, `test_literal_parser_never_evaluates_shell` and `test_process_values_override_defaults`, covering explicit directory/file selection, environment selection, cwd/config fallback, missing selected directory/file, literal `${...}` retention, split-on-first-`=`, process override and empty override. Ensure no subprocess/shell evaluation happens in Python.
- [x] Add `test_wrapper_forwards_argv_and_exit` and `test_shell_defaults_preserve_environment` with fake executables and temporary config only. Copy wrappers/bodies/helper into a temporary fixture checkout; replace only fixed absolute venv prefixes in those temporary copies with the fixture fake-executable prefix, never modify the host venv or add production interpreter overrides for tests. Assert root wrapper forwards spaces/empty arguments and exit 23; helper anchors root cwd from outside cwd; environment overrides both arms/camera defaults; SSH-derived viewer fallback still evaluates in Bash. Stub all Python/uv/viewer/device utilities before running a launcher body; never let a test reach a real device, network check or dataset writer.
- [x] Run each targeted test using fresh scratch. A missing import during collection is an environment/setup failure; establish the intended assertion failure before implementation and record that RED.
- [x] Implement the exact loader signatures and update `voice_policy.read_arms_env`, `calib_capture`, `check_bus` and `read_pose` to consume them. Keep legacy literal parsing and all default values. Do not add local.env or package config inside wheels.
- [x] Move shell bodies, add the two helper functions, and keep all sibling calls absolute. Replace config-file existence checks with selected config paths. Preserve current interpreter choices and argument consumption; retain root cwd. Root wrappers use quoted `exec` delegation. At this checkpoint bodies still target flat Python commands; no premature package-module invocation.
- [x] Install the project editable into `TEST_PYTHON` with `uv pip install --python "$TEST_PYTHON" --no-deps -e "$WORKTREE"` (backend remains constrained); run targeted config/launcher tests to GREEN. Run `bash -n` on the seven wrappers, seven bodies and helper. Review default-value/config diff and commit this checkpoint locally.

### Task 3: Package voice and preserve test identity

Files: move all nine voice modules to `src/so101_test/voice/`; create its inert `__init__.py`; modify the five existing test modules and `tests/conftest.py`; create root `voice_agent.py` and `voice_latency_check.py` stubs; modify `scripts/voice_agent.sh`. Add voice assertions to `tests/test_entry_boundaries.py`.

Consumes: explicit config contract, installed project, launcher helper. Produces: canonical voice module imports, unchanged parser/main interfaces and safe old/new voice entry paths.

- [x] Add `test_voice_patch_targets_canonical_module` for implementation-module identity and patched `say`, and `test_voice_help_stays_inert` in a subprocess with denied policy/hardware/ASR imports. Compare parser defaults and help against baseline, allowing only displayed invocation path differences. Test root stub and `python -m so101_test.voice.voice_agent --help`.
- [x] Establish assertion RED, then move the nine files and change all eager/delayed local imports to relative package imports. Preserve their location relative to key/argument validation. Do not edit model defaults, action queues, policy construction, ASR timing or runner logic.
- [x] Change existing tests to canonical imports. Remove the root `sys.path` insertion in conftest; do not keep root copies of internal voice helpers or module aliases. Keep the existing `say` fixture patching the canonical module.
- [x] Add the two guarded root delegates; switch the voice shell body to `"$VENV/bin/python" -m so101_test.voice.voice_agent`. Preserve VENV override, fake/help camera-lock bypass, cache defaults and environment cleanup.
- [x] Run targeted voice tests to GREEN, including immediate stop, stale answer rejection, stop/quit/home during verification and retry cancellation. They remain in the final full suite; do not duplicate their assertions in new tests.
- [x] Read the source/import diff inline, verify delayed dependencies remain delayed and commit the voice checkpoint.

### Task 4: Move the connected camera and operations cluster

Files: move five camera and four operations modules; create both inert `__init__.py` files; add the remaining nine public Python stubs; update affected `scripts/` bodies; extend `tests/test_entry_boundaries.py` and `tests/test_launchers.py`.

Consumes: Task 2 config/helper and Task 3 canonical package pattern. Produces: the complete grouped package and one implementation per public entry point.

- [x] Add `test_diagnostic_import_is_inert` parametrized over both diagnostics, in isolated subprocesses that deny SDK imports, config/cache reads and device construction. Assert importing either canonical diagnostic and its root stub does none of them. Add controlled-main tests with fake SDKs and fake calibration data to preserve positional defaults, identity/path construction, operation order and printed output without hardware.
- [x] Add `test_adapter_patches_precede_main_once` parametrized over record and teleop adapters, using isolated LeRobot stubs: import does not call external main; original callbacks are captured before replacement; patched callbacks are installed when main executes; importing through a root delegate does not install a second copy. Assert recording uses canonical camera alignment/capture modules. Stub OpenCV and config as needed; do not import every package module.
- [x] Add `test_alignment_stub_preserves_root_cwd` proving its old repository cwd semantics for relative reference/image paths, while other calibration delegates retain caller cwd. Add body-invocation assertions for uv project, real and overridden/default voice interpreters, module argv, root cwd and selected config. Preserve shell positional argument semantics from baseline.
- [x] Run to assertion RED, move the modules and update the two cross-camera imports. Extract diagnostic executable bodies and SDK imports into `main()`, keeping cache identity and bus logic. Extract camera dispatch and adapter external-main calls into guarded main functions. Keep record/teleop patch installation at import, in the same order.
- [x] Add the nine remaining guarded delegates, with the alignment-only root `chdir`. Switch teleop, record and camera-snap bodies to canonical `-m` paths. Use `uv run --no-sync` for project commands after explicit installation. Rollout still calls the real environment's existing `lerobot-rollout`; calibration still calls existing `lerobot-calibrate` with the same arguments.
- [x] Run focused boundary/launcher tests to GREEN and `bash -n`. Review all public entry paths, patch order, config consumers and relative-path semantics inline. Commit the connected migration checkpoint.

### Task 5: Verify distribution, documentation and stable checkout

Files: `tests/test_package_provenance.py`, `README.md`; move `docs/so101-lerobot.html` to `docs/guides/so101-lerobot.html` and historical plan to `docs/plans/voice-agent-plan.md`; update ledger. Modify `pyproject.toml` only if required for package inclusion; preserve the greeting command and dependency constraints.

Consumes: complete package. Produces: verified wheel, installed provenance, full ordinary gate, reviewed commits and usable original checkout.

- [x] Add `test_installed_package_origin_outside_cwd` using installed `so101_test.config` and standard-library-only voice modules, with `PYTHONPATH` unset. Pass expected interpreter and package prefix through test-only subprocess arguments; source tests expect the editable worktree prefix, runtime readback expects each venv site-packages prefix. Assert exact module origins. For editable development, read `direct_url.json` and verify its editable source path; for wheel runtime installs, verify the distribution file list covers all application groups rather than only the greeting. Do not use an import-all check.
- [x] Build with the verified `UV_BIN`: `uv build --wheel --out-dir "$BUILD_ROOT/wheels" "$WORKTREE"`. Record command, backend version, wheel path and SHA256. Inspect the wheel manifest for all 18 application modules and config helper, and absence of checkout env files, stubs and external artifacts.
- [x] Install that exact wheel with `uv pip install --python <exact-real-or-voice-python> --no-deps <exact-wheel>` after checking no active task-owned runtime uses either environment. Save before/after application dependency snapshots and package origins from outside cwd. The known existing environment supplies dependencies; a missing dependency is a closure gate, not a reason to download application upgrades. This approval includes only project installation into those two runtime environments.
- [x] Run the full `tests/` gate with the same project interpreter and all new tests. Preserve baseline skip comparison and actual test counts. Verify the wheel path assertions separately in real and voice environments; safe voice help must not touch hardware or load a policy.
- [x] Move the two docs. Rewrite README in English using the project-local humanizer skill, preserving facts, commands and source literals except intended config/doc/source paths. Document root stub compatibility, explicit installed config, interpreter split, no-sync project setup, and direct Python viewer limitation. Do not add a new teaching guide. Check moved HTML relative links/assets and all changed repository links.
- [x] Run `git diff --check`, final inventory/rename/default comparison and inline self review. Record test commands, JUnit, skips, runtime provenance and limitations in the ledger. Commit final source/docs/checkpoint changes. Do not claim physical or visual validation.
- [x] Recheck original checkout: only expected approved commits, clean status, `main` still an ancestor of the task branch and no new user work. Fast-forward `main` locally with `git merge --ff-only chore/so101-test-organisation`. Stop on divergence or user changes; do not reset, stash, force or push.
- [x] Rebind the project editable install to `/home/matianyi/Projects/so101_test` using `--no-deps`. Check from outside cwd that project module origins resolve into this stable checkout, while real/voice origins resolve into their installed wheel locations. Check safe root voice help and stub-based launcher tests against the stable checkout. If integration/rebind changed tracked content or exposed a failure, repair and rerun the affected gate before completion.
- [x] Report final commit/status, retained evidence, archived runs (none unless explicitly created), remaining scratch deletion candidates, build/wheel hashes and local worktree retention. Leave evidence and worktree in place; no cleanup authorisation is implied.

## Exact pytest gate recipe

Each targeted RED/GREEN command and full suite invocation gets a new run directory, not just the baseline and final gates. The executing agent substitutes a unique label, records cwd/commit, and runs with the exact preflighted Python. Run logs and JUnit go inside this run directory; wheels/builds do not.

```zsh
TASK_ROOT=/data/work/so101-evidence/repo-organisation/20261029-e8a252c0
TEST_PYTHON=/home/matianyi/Projects/so101_test/.venv/bin/python
test -d "$TASK_ROOT" && test -x "$TEST_PYTHON" || exit 1
mkdir -p "$TASK_ROOT/scratch"
pytest_run_dir=$(mktemp -d "$TASK_ROOT/scratch/pytest.XXXXXXXX") || exit 1
mkdir "$pytest_run_dir/tmp" || exit 1
export TMPDIR="$pytest_run_dir/tmp" TMP="$pytest_run_dir/tmp" TEMP="$pytest_run_dir/tmp"
"$TEST_PYTHON" -c 'import os,pathlib,sys,tempfile,pytest,xdist; actual=pathlib.Path(tempfile.gettempdir()).resolve(); expected=pathlib.Path(os.environ["TMPDIR"]).resolve(); print(sys.executable,pytest.__version__,pytest.__file__,xdist.__version__,xdist.__file__,actual); assert actual == expected' > "$pytest_run_dir/tempfile-proof.log" 2>&1 || exit 1
logical_cpus=$("$TEST_PYTHON" -c 'import os; print(os.cpu_count() or 1)') || exit 1
workers=$(( logical_cpus > 8 ? 8 : logical_cpus ))
print -r -- "logical_cpus=$logical_cpus workers=$workers" > "$pytest_run_dir/parallelism.txt"
started_s=$(date +%s)
if "$TEST_PYTHON" -m pytest tests/ -n "$workers" -o tmp_path_retention_policy=failed -o cache_dir="$pytest_run_dir/pytest-cache" --junitxml="$pytest_run_dir/junit.xml" > "$pytest_run_dir/pytest.log" 2>&1; then
  pytest_rc=0
else
  pytest_rc=$?
fi
finished_s=$(date +%s)
print -r -- "exit_code=$pytest_rc elapsed_s=$((finished_s-started_s)) scratch=$pytest_run_dir/tmp" > "$pytest_run_dir/result.txt"
cat "$pytest_run_dir/pytest.log"
test "$pytest_rc" -eq 0
```

For targeted runs replace `tests/ -n "$workers"` with the exact focused file/node selection recorded by its task; the complete final command remains as above. Check the launched workers' tempfile paths through a session fixture in `tests/conftest.py`, with one proof file per worker in the run directory. This fixture must not edit import paths. Parse JUnit to record collected/executed/passed/failed/error/skipped counts; a zero shell exit alone does not establish complete collection. No pipeline is needed; if one is introduced, enable `set -o pipefail` and preserve the pytest status.

## Approval boundary and recovery

This plan is ready for review, not execution. Approval includes the local branch/worktree, checkpoint commits, scoped test tooling, project-only installs and local fast-forward described above. No second worktree-consent question is needed once that scope is explicitly approved. Do not launch an execution worker before confirmation.

On a failed gate, preserve evidence and inspect the running process/logs/outputs before any retry. Repair only the migration boundary, then rerun the affected focused checks and full gate if source changed. A runtime-install failure leaves provenance incomplete; restore a previously recorded project artifact only if available and report the state, without changing application dependencies or caches. Do not remove the worktree while any interpreter refers to it.
