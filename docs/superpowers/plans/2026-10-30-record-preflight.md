# Recording preflight implementation plan

**Goal:** Every record.sh launch checks lighting and side-camera alignment before connecting arms; a failed or unavailable check requires explicit y/Y, with N as the default.

**Architecture:** A camera-only Python module captures bounded samples and compares static regions against the manually accepted 2026-10-30 reference. The shell launcher owns the continuation decision and starts record_viz only after a successful check or explicit override. Unique evidence directories retain outcomes and decisions.

**Spec:** User request in this session; detailed engineering brief retained at `/data/work/so101-evidence/real-robot/record-preflight-implementation/brief.md`.

**Constraints:** Preserve existing collection arguments, task labels, dataset paths and runtime environment. No robot operation during implementation. No automatic baseline update or silent bypass. Keep existing uncommitted tools work. Work in the user's active checkout; do not commit.

- [x] Write failing pure image and mocked launcher tests, including default rejection and explicit override.
- [x] Implement camera-only check, configurable reference and thresholds, bounded capture and evidence.
- [x] Integrate after camera lock and before record_viz, including lock/check errors and EOF handling.
- [x] Document checks and manually established baseline.
- [x] Review patch independently, run full mocked/offline suite and a real camera-only check; fix failures before reporting completion.

Root coordinates, implementer SubAgent writes code and tests, reviewer SubAgent checks the concrete patch. Root verifies camera-only integration and records final test results. Thresholds are engineering starting points, not calibrated millimeter pose guarantees.
