# P0 baseline evaluation

- P0_RUN: `20261029T215724` (provided by user).
- Evidence root: `/data/work/so101-evidence/real-robot/p0-20261029T215724/`.
- Protocol: original 10 control layouts, three rounds per colour, 60 episodes planned; TE=0, MAX_REL=30, 20 fps, 30 seconds maximum per episode. No agent automatic retries.
- Printed layout and recording sheets: `/data/work/so101-evidence/real-robot/p0-print-20261029/so101-p0-layout-and-records.pdf`.
- Planned dataset order under `/data/work/so101-datasets/`:
  1. `eval-p0-20261029T215724-green-r1`
  2. `eval-p0-20261029T215724-red-r1`
  3. `eval-p0-20261029T215724-red-r2`
  4. `eval-p0-20261029T215724-green-r2`
  5. `eval-p0-20261029T215724-green-r3`
  6. `eval-p0-20261029T215724-red-r3`
- Results: pending; recording the run identifier does not establish completion of any trial.

## R1 readback (2026-10-29, ai-station, offline only)

- OBSERVED: green-r1 10 episodes / 3746 frames; red-r1 10 episodes / 3959 frames. All per-episode timestamps step 0.05 s; frame indices continuous; both camera frame counts equal corresponding data rows.
- OBSERVED: final in-bowl green 8/10, red 7/10 (visual review of all side contact sheets / first-last images). Green failures recorded ep6, ep10. Red failures recorded ep4, ep5, ep10. No wrong-colour transport observed in reviewed sheets.
- Actual red recorded-to-layout mapping: 1,2,3,4,5,7,8,9,10,6. All ten planned layouts represented; do not equate recorded episode number to printed row after ep5.
- Green recorded ep4: target A4, distractor detected/visually consistent with C3 rather than planned C2. Retain as extra layout; planned A4/C2 remains missing from strict matched baseline. Other green layouts match.
- Actual adjacency: green 3/5, non-adjacent 5/5 (includes ep4 variant); red 4/5, non-adjacent 3/5.
- Failure review: green ep6/ep10 repeat empty transport; green ep10 target displaced. Red ep4 target moved/lifted but ends on table right of bowl; red ep5 target displaced near bowl without successful placement; red ep10 repeated misses. Red ep2 initial miss followed by successful pickup (26.2 s recorded episode duration). Detailed first-grasp labels for all episodes remain unconfirmed.
- Light stable across R1: side approximately 154 in both; wrist green 162-175, red 159-174. Wrist at high end of training ranges. These full-frame statistics do not certify local exposure, geometry or identical task-start poses.
- Protocol TE=0/MAX_REL=30 based on instructed commands; exact launched command provenance not independently recovered. Do not infer effective clamp events from action-state gaps alone.
- Evidence retained: per-colour contact sheets, first-last images, failure detail sheets, integrity/light JSON, summaries, r1-results.json and analysis helpers. No archives or deletion candidates designated; nothing deleted.
- Next: continue unchanged red-r2 then green-r2; correct green layout row4 to A4/C2. Preserve green-r1 ep4; collect any missing strict-baseline trial in a separately named supplemental dataset.

## P0 complete readback / P2 proposal (2026-10-30, ai-station, offline only)

- Current checkpoint: all six datasets reviewed; 61 source episodes / 22775 frames. Exclude green-r2 recorded ep7 (one frame, 0.05s, target already in bowl) from task denominator; retain source unchanged. 60 task trials / 22774 frames remain.
- All 61 metadata lengths, data frame indices, 0.05s timestamps and both decoded camera counts pass. New helper `review_all.py` handles the extra short episode; old `rollout_sheet.py` failed its max-difference reduction on the one-frame record and was not used as integrity evidence.
- Final outcomes OBSERVED: green r1 8/10, r2 9/10, r3 9/10 => 26/30. Red r1 7/10, r2 6/10, r3 7/10 => 20/30. Overall 46/60 (76.7%). These are final recorded-episode outcomes, not first-grasp rates.
- Exact-layout subset: green 25/29 plus one successful A4/C3 variant; red 20/30. Thus 45/59 exact planned-layout trials, not a perfectly matched 60-trial grid. Missing green A4/C2 third repetition can only be supplemented in separate dataset, never overwrite the variant or failures.
- Actual layout order by recorded ep: green-r2 1,2,3,4,5,6,EXCLUDED,7,8,9,10; green-r3 1,2,3,4,5,7,8,6,9,10; red-r1 1,2,3,4,5,7,8,9,10,6. Other groups original order.
- Green failed recorded eps: r1 6/10, r2 11, r3 10. Red failed recorded eps: r1 4/5/10, r2 1/4/6/7, r3 4/6/7. All outcomes in all-results.csv/json, table aggregation all-summary.json.
- User confirmed 2026-10-30: no assistance, only setup finishing/keyboard use in green-r3 ep9 and red-r2/red-r3 ep1. Do not mark these assisted. Preserve note that green-r3 ep9 starts with hand near bowl and initial full-frame luma is affected.
- Weakest groups: green B2/B1 0/3; red A4/C2 0/3; red D1/C1 0/3; red D4/D3 1/3. These four groups account for 11 of 14 failures. Green D1/C1 2/3, including r3 ep8 success only after a late second attempt; red A1/C3 2/3; red D1/B3 2/3.
- Context contrasts: green B2/D4 3/3 vs B2/B1 0/3; red A4/A3 3/3 vs A4/C2 0/3; red D1/B3 2/3 vs D1/C1 0/3; red D4/B2 3/3 vs D4/D3 1/3. Data/context or trajectory coverage hypothesis supported, causal root not confirmed (n=3 per layout).
- Failure pattern: repeated empty approach/transport and displacement in multiple side/wrist reviews; red A4/C2 also includes cube movement with final outside-bowl placement. Do not count every failure as failure to close the gripper. No complete first-grasp annotation; fields stay null. At least green-r3 ep8 and red-r1 ep2 show miss then final success. Recorded duration is not exact completion time; 30-second green-r3 ep8 is a success, 22.1-second red-r3 ep4 is a failure.
- Lighting: most side first-frame luma 154-156; green-r3 ep9 145.07 with hand occlusion. Wrist range across valid trials 157.61-181.49; red-r2 four high-light successes (eps3/5/8/9), so full-frame brightness does not explain failures by itself. No proof local exposure/white balance/geometry identical. Runtime TE/clamp/stop-reason command provenance not independently recovered; use instructed protocol as intended settings only.
- Proposed P2: 80 accepted clean full expert demos, 40 per colour, 8+32 pilot/main phases. Hard combinations get 60/80; remaining 20 provide contrasts/retention. Counts and controls in p2-proposal.json. Proposal only; no robot command, training, model change, data merge or source edit performed.
- Recommended approach is targeted clean demos before a separate optional recovery batch. Keep training and inference recipes fixed for first comparison; P1 shorter action-block hypothesis remains untested. Keep P0 eval trajectories out of training. Suggested acceptance green28/30, red27/30 and four weak groups >=9/12; thresholds do not establish statistical significance.
- Host/worktree: ai-station; /home/matianyi/Projects/so101_rollout; main at 5cc17c7d92ae16ca233451579dd78508e9b511c3; source clean before analysis. Python /data/work/venvs/so101-real-lerobot-061/bin/python. ROS/Gazebo layers not used; no stack launched or robot movement. Existing processes untouched.
- Image handling: inspected dimensions before display; viewed previews <=1600px long side (side overview 1536x1060 or smaller, detail1280x795, individual frame640x480). Original source videos and earlier original sheets preserved.
- Retained: all six source datasets, 61 episodes including excluded record, all images/previews, integrity/light results, all-results.csv/json, source path/size/SHA256 manifest, summary and P2 proposal. Archived: NONE. Deletion candidates: NONE. Nothing deleted.

## P2 compact collection cards (2026-10-30)

- User requested detailed cards matching prep-20261028-red placement-list style, maximum20 cards/page; PDF preview before any printing.
- Superseding proposal: 30 accepted demos, green10/red20, not the earlier80. Green: B2/B1 x6, B2/D4 x2, D1/B3 x2. Red: A4/C2 x6, D1/C1 x6, D4/D3 x4, A4/A3 x2, D1/B3 x2. Proposed conditions, not executed.
- Cards at p2-cards/p2-collection-cards-30-v1.pdf (2 A4 pages). Page1 G01-G10 + R01-R10; page2 R11-R20 plus shared instructions. placement-list.json/csv are authoritative detailed proposed conditions. Includes per-cube grid-relative3mm offsets, target yaw0/+10/-10deg, consistent V approach and actual-episode/outcome annotation fields.
- V approach proposal: align about20mm above target, smooth final descent about0.5-1s, confirm hold then cube bottom about30mm above table before transfer; avoid forced independent jaw yaw on SO101. Keep bowl/camera/light geometry consistent. These are approximate human teleoperation goals, not certified robot command tolerances.
- Validation: generator assertions pass for30 unique IDs, per-layout counts and text width/height; pdfinfo confirms2 A4 pages. Viewed both1131x1600 previews; original2480x3508 pages preserved. Artifacts include SHA256 manifest.
- Printer: NOT SUBMITTED; waiting for user PDF review/explicit print confirmation as requested. No robot recording/training/merge/source changes. No evidence deleted or archived.

### P2 cards v2: larger layout diagrams

User requested right-hand grid diagrams nearly fill each card height. New review PDF: p2-cards/v2/p2-collection-cards-30-v2.pdf. Grid expanded from115px to238px height within284px card; bowl and labels enlarged proportionally. Text confined to separate left region, approach line shortened while retaining dimensions and shared V instructions. Generator assertions confirm30 unchanged conditions, no text overlaps diagram region,2 A4 pages; visually checked R11 local crop after checking source2480x3508 dimensions. Original v1 retained. No print submitted; user review still pending.

### P2 cards v3: remove repeated approach line

User requested removing approach information from each card. p2-cards/v3/p2-collection-cards-30-v3.pdf removes all repeated approach lines and retains shared page2 V instructions. Placement/rotation conditions identical to v2 (JSON equality verified);20-card page capacity and enlarged diagrams retained. Generator validation passes; R11 crop1145x295 visually checked after inspecting full-page dimensions2480x3508. Previous versions retained. No print submitted; user PDF review pending.

### P2 cards v4: independent colour batches and ACT training datasets

User explicitly requires separate green/red operation batches and recording folders for two separate ACT models. Generated independent1-page A4 PDFs: p2-cards/v4/p2-green-collection-cards-v4.pdf (batchA G01-G10), p2-cards/v4/p2-red-collection-cards-v4.pdf (batchB R01-R20). Page headers display dataset path and exact TASK. Green dataset planned /data/work/so101-datasets/real-cube-bowl-p2-green-20261030; red planned /data/work/so101-datasets/real-cube-bowl-p2-red-20261030; both absent at preflight, not created. Green expert data only augments original93 green episodes (103 if all10 accepted); red only augments original92 red episodes (112 if all20 accepted). Separate JSON/CSV plans, command text and batch manifest retain colour binding. No combined colour training dataset proposed. Original30 placement conditions unchanged (JSON equality verified). PDFs each1 A4 page, previews1131x1600 inspected after dimension checks. No robot command/training/printing executed; earlier PDF-review-before-print requirement remains active.

User requested image inspection policy persisted: created /home/matianyi/Projects/so101_rollout/AGENTS.md with four requested rules (inspect dimensions first; default preview long edge<=1600px; preserve original; crop small text/details; avoid multiple consecutive full-size large images). Readback confirms exact instructions. Only source change is new untracked AGENTS.md; no commit made.

### P2 cards v5: emphasize nonstandard placement conditions

User requested red bold emphasis for nonstandard angles/positions. Separate PDFs in p2-cards/v5/ now highlight all nonzero signed offset tokens, nonzero angle tokens and variant card titles in dark red bold. Zero values remain black. Footer explains highlighting. Per-colour30 conditions and dataset/task bindings unchanged versusv4 (JSON equality verified). Generator width/count assertions pass; source2480x3508 checked before viewing1145x590 local G09/G10 crop to verify red bold+3mm/+10/-10deg display. Previous versions retained; no print submitted.

### P2 v5 print submission

User explicitly requested printing all batches. Submitted latest green10 and red20 v5 PDFs together to HP_SmartTank_660, one copy of each, A4 single-sided colour (print-color-mode=color, ColorModel=RGB) to preserve red bold nonstandard conditions. Both source PDFs verified one A4 page each; printer idle/enabled before submission. lp exit0, accepted request HP_SmartTank_660-5 (2 files / 2 pages). Submission confirmed; physical paper delivery not independently observed. No earlier PDF versions printed in this submission.

## P2 full80 scope restored and remaining50 printed (2026-10-30)

- User clarified initial printing was incomplete and explicitly confirmed: complete total80 (40 green/40 red), print only remaining50, preserve already-printed30. This supersedes the earlier30-only scope; no robot recording/training authorization inferred.
- Supplemental cards generated under p2-cards/supplement50/: green G11-G40 (30 cards/2 A4 pages), red R21-R40 (20 cards/1 A4 page). Each PDF contains one target colour only. Large diagrams, no repeated per-card approach line, red bold nonzero offsets/angles retained. Three1131x1600 previews checked after dimension inspection; source2480x3508 PNGs retained.
- Plans: supplemental green uses /data/work/so101-datasets/real-cube-bowl-p2-green-extra-20261030; red uses /data/work/so101-datasets/real-cube-bowl-p2-red-extra-20261030. Both absent before printing; only planned paths, no dataset created. Local supplement ep1 maps to G11/R21; actual episode IDs must be annotated. Existing first30 data folders remain separate. Green training merges original93 + first10 + extra30 =>133 if accepted; red original92 + first20 + extra20 =>132 if accepted. Separate ACT models.
- Full80 includes original30 conditions byte-for-field unchanged and50 additions. Unique IDs G01-G40/R01-R40 verified, each colour exactly40. Green counts: B2/B1 20, D1/C1 8, B2/D4 4, D1/B3 4, A1/A2 2, D4/D3 2. Red counts: A4/C2 12, D1/C1 12, D4/D3 8, A1/C3 2, A4/A3 2, D1/B3 2, D4/B2 2. Preserve2 already-printed D1/B3 red controls in place of2 original-proposal A1/C3; explained to user before printing. No historical card renumbering or change.
- Machine manifests: supplement-batch-manifest.json, complete80-placement-list.json, separate colour JSON/CSV and copyable command text, artifact-sha256.json. Per-layout totals/text bounds validated by generator assertions; pdfinfo confirms2+1 A4 pages.
- Printed only supplementary PDFs, each1 copy, A4 single-sided colour: lp exit0, accepted job HP_SmartTank_660-6 (2 files/3 pages). Previous job5 printed initial30; no duplicate initial cards in job6. Physical paper delivery not independently observed.
- Retained all plans, PDF versions, original PNGs/previews, source datasets and logs. Archived NONE; deletion candidates NONE; nothing deleted. Source remains only newly requested AGENTS.md, no commit. No robot/recording/training command executed.

## Offline tools migrated into repo (2026-10-30)

User requested reusable tools/ directory, concrete collection commands, SmolVLA data advice and root/SubAgent work split. Implemented7 offline CLIs plus common helpers, reviewed input plans/annotations, source provenance, requirements, README and reference commands. Source worktree main5cc17c7, no commit/push. Details tracked in docs/experiments/offline-tools-experiment-ledger.md; verification artifacts in tools-migration/. Legacy migration, documentation and read-only audit delegated after explicit user authorization; root integrated fixes and verified259 tests with8 workers, all61 real-data episodes,46/60 manually reviewed outcomes,80 unchanged card conditions. Independent source-data folders and robot runtime environments retained. One language-conditioned SmolVLA is the stated goal; preserve exact labels for a later derived multitask export, current two ACT training sources remain separate. Current80-plan paired physical cell conditions1/12, not the whole265-data audit. No robot, camera, training, new printing, merge, commit or push performed in migration. Generated outputs remain in evidence; no source data/evidence deleted.
