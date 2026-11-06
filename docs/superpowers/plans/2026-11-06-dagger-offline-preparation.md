# DAgger offline preparation implementation plan

> **For agentic workers:** Use subagent-driven-development for the independently assigned units below. This plan records the user's approved parallel preparation scope; hardware integration is a later gate.

**Goal:** Prepare an auditable collection protocol, pure offline control-state logic, expert-segment data validation, and a twelve-attempt SmolVLA v2 pilot manifest.

**Architecture:** Keep new preparation modules independent of production rollout and serial/camera drivers. A state machine requests adapter effects; it cannot certify hardware actions. Data validation and case selection consume explicit provenance rather than infer successful demonstrations from file completeness.

**Tech Stack:** Python standard library, existing pytest environment, Markdown and JSON.

**Spec:** User-approved sequence: policy execution → pause/hold → bounded stable leader alignment → READY → expert correction → end. No return to autonomous policy in the first pilot. Existing historical evidence is indexed in `docs/baselines/pre-dagger-20261106/README.md`.

## Global constraints

- Do not run hardware, training, recording, or alter existing rollout behavior during preparation.
- Use SmolVLA v2 initially; preserve separate policy/version provenance for ACT and other versions.
- Keep failed/assisted historical rollouts as baseline evidence, not expert training examples.
- Preserve requested actions separately from successfully sent follower targets and measured states.
- Never train across policy/alignment/hold/expert boundaries or split one source session across train and validation.
- Normal expert completion stops following and awaits supported release; faults must not wait for normal confirmation.

## Parallel units

- [x] State machine: `src/so101_rollout/dagger/state.py`, focused tests and state protocol. Validate transition order, invalid/stale events, generation invalidation, timeouts, terminal handling, and explicit adapter acknowledgements.
- [x] Data contract: `src/so101_rollout/dagger/data.py`, focused tests and data protocol. Validate units/timestamps/control origin, accepted correction segments, boundary-safe chunks, and source-session separation. Record limitations of historical action semantics.
- [x] Candidate manifest: `docs/experiments/dagger-pilot-cases-20261106.{md,json}`. Cross-check every historical case against the frozen archive, use six green/six red attempts, and label repeated layouts explicitly.
- [x] Root review: run combined offline tests, parse manifest, check links and references, and produce a preparation entry point distinguishing completed offline work from pending integration.

## Review focus / integration gates

1. A recorded pause acknowledgement is not proof that the real scheduler or motor command stream stopped: integration must instrument queue clearing, old-result rejection, and the last sent goal.
2. Leader-relative takeover requires a fresh reference and unchanged first follower target; validate with hardware traces before collection.
3. A successful send is not proof of motion or task success; retain observed joint state and operator acceptance separately.
4. Existing datasets may store requested rather than post-limit targets. Mixing them with corrected data requires an explicit action-semantics audit.
5. A successful autonomous rollout is not a recovery demonstration. Keep all attempts, require genuine policy-visited correction states, and do not provoke unsafe failures to fill quotas.

## Completion boundary

Offline preparation does not authorize autonomous hardware execution. The next review must inspect the near-alignment hardware results, implement real adapters/recording, validate one instrumented handover, then admit pilot correction data. No production DAgger readiness claim follows from passing pure-unit tests.

## Verification receipt

2026-11-06: root independently ran 148 focused tests covering the new state/data contracts, existing handover probes, and asynchronous engine; all passed. Candidate manifest references, six-green/six-red ordering, nine historical failure IDs, layout/task correspondence, document links, and `git diff --check` passed. No hardware execution, formal collection, training, commit, or push was performed.
