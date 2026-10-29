# so101_test source organisation design

Status: proposed for review. Selecting directory organisation does not approve execution of the detailed plan. This document and its [implementation plan](../plans/2026-10-29-so101-test-organisation-plan.md) require explicit confirmation before source moves, installations or tests.

## Intent and scope

Turn the existing greeting-only `src/so101_test` package into the owner of the application. Group related source files without changing robot behaviour, policy parameters, cancellation semantics, device identities or artifact locations. Commands must remain usable from `/home/matianyi/Projects/so101_test` after integration.

The inspected baseline is `main` at `c724e389536e56875a54642b230d48532dfbde35`, with 41 tracked files, 18 functional root Python modules and seven shell launchers. The checkout was clean before planning. This is the direct LeRobot application on ai-station; ROS packages and simulator stacks are outside this change.

The prior [organisation analysis](/data/work/so101-evidence/repo-organisation/20261029-e8a252c0/inputs/organisation-analysis.md) records the exhaustive inventory and alternatives. The coordinator retained this verified copy in the registered evidence root. The contracts below are sufficient to implement the selected approach.

## Approaches considered

| Approach | Tradeoff | Decision |
| --- | --- | --- |
| Sort sibling scripts into `apps/` and `tools/` | Fewer import changes, but application installation and test provenance remain separate problems. | Considered. |
| Use the existing `src/so101_test` package | Requires explicit configuration and project visibility in each interpreter; gives one implementation and canonical imports. | Selected in the preceding discussion. |
| Package voice only | Reduces the first move, but leaves two distribution models and the recording/camera migration unfinished. | Considered. |

The detailed choices in this design are proposals for the user's review. They do not imply approval of an unseen implementation.

## Source layout and ownership

| Destination | Existing files and responsibility |
| --- | --- |
| `src/so101_test/voice/` | `voice_agent.py`, `voice_runner.py`, `voice_policy.py`, `voice_intent.py`, `voice_llm_intent.py`, `voice_verify.py`, `voice_asr.py`, `voice_fake_robot.py`, `voice_latency_check.py`: orchestration, policy use, local/LLM intent, verification, speech and replay. Preserve filenames and current boundaries. |
| `src/so101_test/camera/` | `calib_capture.py`, `calib_intrinsics.py`, `calib_extrinsics.py`, `calib_targets.py`, `align_side.py`: calibration and alignment. |
| `src/so101_test/operations/` | `record_viz.py`, `teleop_viz.py`, `check_bus.py`, `read_pose.py`: LeRobot adapters and read-only diagnostics. |
| `src/so101_test/config.py` | Explicit config-directory selection and literal env-file reading, shared by the four existing `arms.env` readers. |
| `config/` | Move `arms.env` and `camera.env` unchanged. These are checked-in non-secret device and camera defaults. |
| `scripts/` | Move the bodies of all seven shell launchers, preserving their names. `scripts/lib/common.sh` owns repository anchoring and default loading. |
| `tests/` | Keep existing filenames; import canonical package modules. Add only the migration-boundary tests listed in the plan. |
| `docs/guides/so101-lerobot.html` | Move the existing teaching HTML and check its links. |
| `docs/plans/voice-agent-plan.md` | Move the historical voice plan without rewriting historical claims. |

Add inert `__init__.py` files to the three groups. Keep the lightweight package root and existing `so101-test` greeting command. Keep dependency constraints, `.python-version` and `uv.lock` unchanged unless the packaging tool requires a local-project metadata refresh; any such diff must contain no dependency resolution changes.

## Public entry points

The seven root shell names remain: `voice_agent.sh`, `teleop.sh`, `record.sh`, `rollout.sh`, `calibrate_follower.sh`, `calibrate_leader.sh`, `camera_settings.sh`. Each computes its own absolute root and uses `exec` to call `scripts/<same-name>` with `"$@"`. The scripts still run with repository-root cwd, so relative policy and dataset arguments retain their current meaning. No new passthrough arguments are added to bodies that currently consume only positional arguments or ignore extra arguments.

Retain root Python forwarding stubs for exactly these command paths: `voice_agent.py`, `voice_latency_check.py`, `calib_capture.py`, `calib_intrinsics.py`, `calib_extrinsics.py`, `calib_targets.py`, `align_side.py`, `check_bus.py`, `read_pose.py`, `record_viz.py`, `teleop_viz.py`. The last two preserve the named LeRobot adapters as callable tools. All other voice helpers move without root copies. The visible root stubs are a compatibility cost; removing them requires a later decision.

A Python stub sets `SO101_CONFIG_DIR` to its sibling `config/` only when that variable is absent, then delegates under `if __name__ == "__main__"` to the canonical module's `main()`. It never changes `sys.path` or re-exports helper objects. Keep arguments, output and exit status intact. Package tests never import these stubs. Preserve caller cwd for direct calibration tools; the root `align_side.py` stub alone retains that command's current repository-root `chdir`. The canonical alignment module uses caller cwd, with no dependency on its installed source directory.

Use `python -m so101_test.<group>.<module>` as the new package CLI. Modules needing an extracted entry boundary receive `main() -> None` and a guarded call: `calib_capture`, both diagnostics and both visualization adapters. Existing main signatures stay unchanged. Avoid a second set of console-script names; installed module entry points cover the new interface.

## Configuration contract

`resolve_config_dir(explicit: str | pathlib.Path | None = None) -> pathlib.Path` selects an explicit directory, then `SO101_CONFIG_DIR`, then `Path.cwd() / "config"`. It resolves the selected path and reports a missing directory clearly. An explicit or environment-selected invalid directory must fail rather than fall back. It never climbs installed parents or assumes that a wheel lives inside a checkout.

`read_env_file(path: str | pathlib.Path) -> dict[str, str]` preserves the existing split-on-first-`=` parser for non-comment assignment lines. It performs no shell evaluation, variable substitution or quote/comment reinterpretation. `load_arms_env(path: str | pathlib.Path | None = None) -> dict[str, str]` uses the explicit file when provided, otherwise `resolve_config_dir() / "arms.env"`, then overlays process environment values for keys present in the file. Preserve `voice_policy.read_arms_env(path=None)` as a delegating compatibility function. The four consumers are `voice_policy`, `calib_capture`, `check_bus` and `read_pose`.

For Bash, `scripts/lib/common.sh` provides `so101_init` and `so101_source_defaults FILE`. `so101_init` finds root from the helper's fixed location, changes cwd to that root and exports an absolute `SO101_CONFIG_DIR`, honouring an existing override. The default loader reads the trusted env file with Bash `source`, preserving `${...}` expansions. It snapshots already-set configuration keys, sources the file, restores those values including explicitly empty values, and exports the resulting known keys. Extract key names only from assignment lines; do not evaluate arbitrary text to discover keys. Source `arms.env` first and `camera.env` only in workflows that already use it.

Effective precedence is existing CLI handling, then explicit process environment, then checked-in defaults. Preserving externally exported device/camera values is a deliberate, bounded correction to the old unconditional shell assignments and Python file-only reads. Keep the literal defaults unchanged and test this correction explicitly. There is no new `local.env` layer.

The Python parser leaves shell expressions as literal strings. Bash launchers export the resolved viewer variables, so their Python children use the same values. Direct Python calibration retains its historical unevaluated viewer default unless the caller supplies `RERUN_VIEWER_HOST`; document this existing limitation rather than adding a shell interpreter or a second expansion language. Hardware literals and numeric camera values remain usable by Python.

Configuration is outside the wheel. Root stubs and shell wrappers supply checkout config; installed commands outside a checkout use an explicit `SO101_CONFIG_DIR`. Pure `so101_test` imports and voice `--help` do not require config. Diagnostics read config only inside `main()`.

## Imports and runtime boundaries

Use package-relative imports inside voice, `from .calib_capture import Preview, open_cam` in camera alignment, and `from ..camera import align_side` in recording. Keep `record_viz -> align_side -> calib_capture` intact. Keep policy, replay and ASR imports at their existing delayed boundaries. `voice_runner` and `voice_intent` remain standard-library-only.

Move all executable bodies of `check_bus` and `read_pose`, including SDK imports, config/cache reads, bus construction and connection, inside `main()`. Importing these diagnostics must require neither hardware SDKs nor device access. Preserve their current positional semantics, calibration identity, connection order, output and exit behaviour. Do not invent a `--help` protocol for tools that lack one.

Keep the import-time patch installation and its order in `record_viz` and `teleop_viz`. Their `main()` functions call the existing LeRobot entry only after those patches exist. Root stubs import the canonical implementation once; they never execute a second copy through `runpy`. Stubbed subprocess checks cover the captured original functions, patched callbacks and main-call order. No blanket import-all test is allowed.

Existing tests import the implementation module, including `from so101_test.voice import voice_agent`. This preserves the identity patched by `monkeypatch.setattr(voice_agent, "say", ...)`. Remove `tests/conftest.py`'s root `sys.path` insertion after installed imports work. Existing stop, quit, home, in-flight answer invalidation and retry tests remain in the ordinary suite.

## Environments, installation and artifacts

Preserve interpreter choices: calibration/teleoperation use the uv project environment; recording/rollout use `/data/work/venvs/so101-real-lerobot-061`; voice uses `/data/work/venvs/so101-voice-lerobot-061`, retaining its `VENV` override and its removal of `PYTHONPATH`, `AMENT_PREFIX_PATH` and `COLCON_PREFIX_PATH`. Camera snap keeps the real environment. Use `uv run --no-sync` after explicit project-only installation, so launchers do not resolve or upgrade application dependencies.

Test with the stable checkout's exact `.venv/bin/python`, after verifying it. Approval includes adding missing test tooling there (`pytest==9.2.0`, `pytest-xdist>=3,<4`, and their missing support dependencies), with before/after package records and no application dependency upgrades. The read-only inventory found pytest 9.2.0 in the voice environment, no xdist there, and no pytest in the project environment; executable preflight must repeat this at execution time. Build-backend provisioning is limited to the existing `uv_build>=0.12.17,<0.13.0` constraint.

Use project-only `--no-deps` installs. A verified wheel goes into the real and voice runtime environments. The project environment may use an editable install while developing, then must be rebound to `/home/matianyi/Projects/so101_test` after integration. Verify package origins outside repository cwd for all three environments. Never leave an operational environment pointing at a disposable worktree.

All evidence uses `/data/work/so101-evidence/repo-organisation/20261029-e8a252c0`. Builds and wheels go under `/data/work/so101-build/repo-organisation/20261029-e8a252c0/`; record their paths, SHA256 and reproducing commands in the evidence root. New venvs belong under `/data/work/venvs/`, models under `/data/work/models/`, datasets under `/data/work/so101-datasets/`, policies under `/data/work/so101-policies/`, and untracked one-off helpers under `/data/work/so101-tools/`. Existing `HF_HOME=/data/models/huggingface`, `TORCH_HOME=/data/models/torch`, calibration caches, model paths, policy paths, evidence defaults and sealed roots stay where they are. This change moves source, not external artifacts.

## Execution and acceptance

Approval covers creating an ignored `.worktrees/repo-organisation` worktree on local branch `chore/so101-test-organisation`, local checkpoint commits, and fast-forwarding the original clean `main` checkout after checks. Start by committing only the approved documents and required `.worktrees/` ignore rule, then create the worktree. Recheck that no user changes appeared before integration; if they did, stop integration without overwriting or stashing them. No remote push is included.

Use new GPT-6.1 Sol / High subagents for concrete execution tasks, as explicitly requested in this session. Each executing Sol agent performs inline self review. This session instruction replaces the repository's default `dst` execution method; no `dst`, Astra or independent-reviewer dispatch is part of this plan.

Acceptance is baseline and final full `tests/` with xdist workers `min(8, os.cpu_count() or 1)`, plus focused config, wrapper, provenance and guarded-import checks. Each pytest invocation gets fresh NVMe scratch inside the registered root, exact-interpreter tempfile proof, JUnit, elapsed time, actual exit status and skip count. A missing dependency is an environment gate, not a source RED. No ROS gates, benchmark suite, arm motion, camera capture, ASR, network/API request or policy-loading fake run is needed. Those remain outside this approval.

Completion reports retained evidence, archived runs and scratch deletion candidates separately. Do not delete evidence, archived runs, worktrees or external artifacts without explicit authorisation. Physical and visual acceptance are N/A because this scope deliberately performs no hardware or GUI run.
