# SO101 rollout rename ledger

task_id: 20261029-so101-rollout
goal: Rename active project and GitHub repository to so101_rollout.
success_contract: New stable path, imports, console command, managed wheel provenance and GitHub repository identity pass; unrelated distributions and historical artifacts preserved.
worktree: /home/matianyi/Projects/so101_rollout
branch: main
base_commit: 424d1ded82e0d11b8b26747fcc2b84c0a9bef1e8
current_commit: 4f24175eee79ce455b4f6a464274f484cf8b365a (validated local rollout; final evidence commit follows)
evidence_root: /data/work/so101-evidence/project-rename/20261029-so101-rollout
confirmed_conclusions: Local rename, README, environments and worktrees verified; GitHub repository ID 1434336506 now has full_name terryma2024/so101_rollout; remote refs unchanged; no commits pushed.
disproven_routes: NONE
open_hypotheses: NONE.
latest_checkpoint: CP-COMPLETE
next_experiment: NONE (complete)

## CP-PLAN

Planning documents prepared; no implementation, install, test, directory rename, commit, push or API mutation. No owned runtime processes. Preserve all existing sessions and the retained repo-organisation worktree. Next action: obtain explicit plan approval, then preflight the current state before execution. Retained: registered evidence root. Archived: none. Deletion candidates: none.

## CP-LOCAL-1

Approval received for local and GitHub rename. Preflight: main at `424d1ded82e0d11b8b26747fcc2b84c0a9bef1e8`, seven commits ahead of origin, retained clean `repo-organisation` worktree, no robot or pytest process. Snapshot at E: distribution lists for root (259), real (284), voice (297); old project installation files; 52 root `.venv` path-bearing files with SHA256 manifest. Negative probe confirmed `so101_rollout` package and command absent before source change. Isolated worktree: `.worktrees/so101-rollout-rename` on `chore/so101-rollout-rename`.

Baseline controlled xdist test run `pytest.ISBw0nI7` failed before collection because ROS `launch_testing` auto-loading imports unavailable `lark`. Retained its log. Ruling: disable unrelated pytest entry-point auto-loading and load xdist explicitly (`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, `-p xdist`) for controlled runs — this preserves test scope and uses the installed xdist plugin — if wrong, unrelated plugin behavior is not exercised. Retry `pytest.VJV2mcsh`: 241 passed, controller plus eight workers wrote tempfile proofs.

Ruling: user requested README update after directory migration, so the source/active test rename will be committed first, followed by README edit and verification at the final stable path — this temporarily leaves README stale within the local-only intermediate commit — if wrong, an intermediate checkout is briefly inconsistent until rollout completes.

## CP-ISOLATED

Source identity changed to `so101_rollout` and distribution/command to `so101-rollout` without dependency edits. The lockfile diff changes only the local project name. Existing provenance, launcher, boundary and config tests passed 95/95 in `pytest.sCXOmmY4`; full ordinary suite passed 241/241 in `pytest.AcduNKAm`, each with controller and eight worker tempfile proofs. `git diff --check` passed and active tracked old-name scan found only the intentionally pending README. No hardware, GUI or benchmark run. README remains pending until after stable directory migration per user request. Retained all evidence runs; deletion candidates only their scratch directories after readback (no deletion performed).

## CP-LOCAL-DEPLOY

Stable main fast-forwarded to `6a382bb70e42ba1a002859780076c205309b1808` after backing up the three original untracked planning documents under E and confirming the committed copies preserve their bytes (ledger extends them). Built pre-move wheel at `/data/work/so101-build/project-rename/20261029-so101-rollout/pre-move/so101_rollout-0.1.0-py3-none-any.whl` (SHA256 `06af09f9750cbc536b1ce461f98a2843bc70613b12cf56dea2c2ed6d6b66b08c`); preserved and hashed prior old-name wheels. Installed only project distributions in managed real/voice environments. Moved checkout to `/home/matianyi/Projects/so101_rollout` and repaired both retained nested worktrees; all three worktrees have expected branches and clean status.

Root `.venv`: removed old and temporary editable project distributions, rewrote the exact old checkout prefix in 48 inventoried text files, repaired 16 package RECORD files, updated the activation and `pyvenv.cfg` prompt, and installed the new editable project from the stable path. Original files and RECORDs are backed up under E. Ruling: moved the ignored `src/so101_test/` bytecode-only tree into E with hashes — its remaining directories exposed a stale namespace import despite removal of tracked source — if wrong, old bytecode is no longer at its original ignored path, but it is preserved for rollback.

Updated README after the move as requested, retaining the explicitly historical original initialization command. Ruling: rebuilt the final wheel after the README update and replaced only the project wheel in each managed environment — this keeps installed wheel metadata aligned with the new README while preserving the pre-move wheel — if wrong, both wheels are retained and hashes distinguish them. Final wheel: `/data/work/so101-build/project-rename/20261029-so101-rollout/final/so101_rollout-0.1.0-py3-none-any.whl`, SHA256 `df63d3a8d13cb59f169b48710205821ae04d076ff9281089b2e621c5cb8b718e`.

External neutral-cwd provenance probe passed in root editable and real/voice immutable-wheel modes. It checked exact interpreters, module origins, direct URLs, independently computed wheel hash and installed package bytes; old distribution and import are absent in all three environments. Actual root `pytest --version` (9.2.0), `so101-rollout` greeting, repaired shebang/activation prompt and `voice_agent.sh --help` passed. Controlled stable-path full suite `pytest.O8PxeeCv`: 241/241 passed, zero skips/failures/errors, controller plus eight worker tempfile proofs. Independently verified all 43 repaired third-party launcher RECORD hashes/sizes, all unrelated distribution lists unchanged (root 258, real 283, voice 296), no old checkout prefix in root `.venv`, and active old-name scan found only the historical README initialization line. Camera module from neutral cwd requires explicit `SO101_CONFIG_DIR` as documented; its `--help` usage text exits 1 by existing CLI convention, so no hardware path was invoked. Final audit and 265 artifact paths/hashes are registered under E. Retained: all test runs, wheel versions, installation backups, worktrees and evidence. Archived: ignored old-name bytecode under E. Deletion candidates: scratch runs and superseded environment backups after readback; nothing deleted.


## CP-COMPLETE

Coordinator independently reviewed source/launcher/provenance/lockfile and final README diffs, root environment repair implementation, wheel manifest and final JUnit (241 tests, zero failures/errors/skips). No blocking review finding. GitHub plugin does not expose repository rename; used secure REST fallback with configured credentials kept out of argv, output and evidence. Rechecked administrator access, absent target name and unchanged remote refs immediately before PATCH. Readback confirms immutable repository ID `1434336506`, full_name `terryma2024/so101_rollout`, default branch `main`. `origin` fetch/push URL is `git@github.com:terryma2024/so101_rollout.git`; advertised refs are byte-for-byte unchanged. No push performed: the original seven local commits and the three migration/evidence commits remain unpublished (main ahead 10, behind 0 against origin/main after this checkpoint commit).

Evidence: sanitized `github-preflight.json`, `github-renamed.json`, `remote-refs-before.txt`, `remote-refs-after.txt`, and `coordinator-artifact-hashes.json` under E. Retained all test runs, worktrees, wheels and environment rollback backups. Archived old ignored bytecode is retained under E. Scratch and superseded backups remain deletion candidates; nothing deleted.
