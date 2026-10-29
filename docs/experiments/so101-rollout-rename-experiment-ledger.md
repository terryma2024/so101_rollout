# SO101 rollout rename ledger

task_id: 20261029-so101-rollout
goal: Rename active project and GitHub repository to so101_rollout.
success_contract: New stable path, imports, console command, managed wheel provenance and GitHub repository identity pass; unrelated distributions and historical artifacts preserved.
worktree: /home/matianyi/Projects/so101_test
branch: main
base_commit: 424d1ded82e0d11b8b26747fcc2b84c0a9bef1e8
current_commit: 424d1ded82e0d11b8b26747fcc2b84c0a9bef1e8
evidence_root: /data/work/so101-evidence/project-rename/20261029-so101-rollout
confirmed_conclusions: Existing root environment requires absolute path repair; local main is seven commits ahead of origin/main; coordinator verified GitHub repository ID 1434336506, administrator access and availability of so101_rollout.
disproven_routes: NONE
open_hypotheses: NONE at planning stage; recheck external state before mutation.
latest_checkpoint: CP-PLAN
next_experiment: NONE (awaiting plan approval)

## CP-PLAN

Planning documents prepared; no implementation, install, test, directory rename, commit, push or API mutation. No owned runtime processes. Preserve all existing sessions and the retained repo-organisation worktree. Next action: obtain explicit plan approval, then preflight the current state before execution. Retained: registered evidence root. Archived: none. Deletion candidates: none.

## CP-LOCAL-1

Approval received for local and GitHub rename. Preflight: main at `424d1ded82e0d11b8b26747fcc2b84c0a9bef1e8`, seven commits ahead of origin, retained clean `repo-organisation` worktree, no robot or pytest process. Snapshot at E: distribution lists for root (259), real (284), voice (297); old project installation files; 52 root `.venv` path-bearing files with SHA256 manifest. Negative probe confirmed `so101_rollout` package and command absent before source change. Isolated worktree: `.worktrees/so101-rollout-rename` on `chore/so101-rollout-rename`.

Baseline controlled xdist test run `pytest.ISBw0nI7` failed before collection because ROS `launch_testing` auto-loading imports unavailable `lark`. Retained its log. Ruling: disable unrelated pytest entry-point auto-loading and load xdist explicitly (`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, `-p xdist`) for controlled runs — this preserves test scope and uses the installed xdist plugin — if wrong, unrelated plugin behavior is not exercised. Retry `pytest.VJV2mcsh`: 241 passed, controller plus eight workers wrote tempfile proofs.

Ruling: user requested README update after directory migration, so the source/active test rename will be committed first, followed by README edit and verification at the final stable path — this temporarily leaves README stale within the local-only intermediate commit — if wrong, an intermediate checkout is briefly inconsistent until rollout completes.

## CP-ISOLATED

Source identity changed to `so101_rollout` and distribution/command to `so101-rollout` without dependency edits. The lockfile diff changes only the local project name. Existing provenance, launcher, boundary and config tests passed 95/95 in `pytest.sCXOmmY4`; full ordinary suite passed 241/241 in `pytest.AcduNKAm`, each with controller and eight worker tempfile proofs. `git diff --check` passed and active tracked old-name scan found only the intentionally pending README. No hardware, GUI or benchmark run. README remains pending until after stable directory migration per user request. Retained all evidence runs; deletion candidates only their scratch directories after readback (no deletion performed).
