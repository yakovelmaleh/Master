# Milestone 1 handoff to MAster SLM

## Authorized T5-first / automated T4 follow-up, November 11, 2026

This section supersedes earlier scope restrictions below. The updated
coordination plan in the original Master checkout was read, including
"Research decision after the 20-story text review." The completed review
sheet's hash/count/status was checked without using its answers to define
training labels, tune boundaries or estimate population rates. The saved
session handoff containing the user-supplied successful CI replay output was
read. The full machine CI artifacts remain on the cluster and are a mandatory
runtime input/hash/configuration gate before this new analysis consumes them.

### Current status: implementation, not research findings

| Work | Implemented | Actual execution |
|---|---|---|
| T5 length/empty/repetitive/reference/duplicate diagnostics | Yes; training-defined bins, frozen literal flags, existing support gates and paired AUC-PRC intervals | Synthetic validation only; real cluster analysis pending |
| T5 chronological shift | Yes; per-project/split/K distributions and support | Synthetic validation only; real cluster analysis pending |
| T5 frozen-vector neighbors | Yes; training-only bounded bank, self exclusion, duplicate sensitivity and per-class disagreement | Synthetic validation only; cache inventory pending on cluster |
| T4 label-blind grouping | Yes; training-only bounded spherical k-means, fixed stability check, outlier rule and numeric profiles | Synthetic validation only; real embedding coverage unknown |

**No new substantive findings or project/K effect estimates can yet be
reported.** Evidence for the review-inspired hypotheses is not evaluated
until the user-operated job reads the successful source run. Do not treat
fixture counts or passing tests as research results.

### Input audit and boundaries

- Successful source run: `/home/yakovelm/master-hf/diagnostics/diag-m1-20261109-02/`.
  Reconciliation: `error-analysis/human-review-01/ci_reconciliation.json`
  and its status/hash manifest. The new runner verifies both cells and their
  original diagnostic configuration, and preserves both methods without a rerun.
- Completed human text review: `/Users/yakovelmaleh/Downloads/review_sheet_completed.csv`,
  20 rows reviewed, all 20 label-verification fields unavailable; SHA256
  `07322a5e59dc95998798dedccccb5e33d88c1d3bdb334255c52387f19eb2db47`.
  No reviews become model-training labels or automatic clarity annotations.
- No local successful cluster-run copy, embedding cache or original full CI
  JSON was found at the checked paths. Older local M1 runs remain partial
  and are not substituted for the completed cluster source.
- Available original HF producer fingerprint:
  `974b8eebd00626edaa8d1b985055722bdaf3dd4d428612dfa6d47863abe771fe`.
  It matches both sealed HF reports' recorded producer fingerprints. Actual
  saved cache keys/rows/bytes still require cluster inspection.
- Historical embeddings bind ordered text/model/configuration/versions in
  their `.npy` filename. No historical numerical checksum exists in that
  writer; this limitation remains explicit. Matching producer code, exact
  cache keys, shape/norms and observed byte hashes are required.
- Source inspection shows train/validation caching, not test embedding
  caching. Missing test caches block dependent test analyses, not independent
  T5. No embeddings are regenerated and no models are loaded.
- No overlapping T4/T5 implementation was found in the inspected task
  directories/worktrees or recent coordination history. This does not claim
  knowledge of unsynchronized work elsewhere.

### Code and configuration

Isolated worktree: `/Users/yakovelmaleh/code/Master-diagnose-t5-characteristics`.
Branch: `user/yakovelmaleh/diagnose-t5-characteristics`, based on merged
`origin/main` at `956f721`. The original dirty checkout and its updated plan
were not modified. No commit, PR, push, external notification or cluster
connection/submission was performed.

Changed/added within `Tasks/diagnose-instability-models/`:

```text
configuration/milestone2.json
scripts/milestone2_text.py
scripts/milestone2_embeddings.py
scripts/run_milestone2.py
scripts/diagnostic_config.py
scripts/support.py
cluster/submit_jobs.py
tests/test_milestone2.py
README.md
HANDOFF.md
```

Default configuration: seed 20261111; project-specific training word-count
quartiles; minimum 50 rows/10 positives/10 negatives; 500 non-circular paired
row-block resamples, block size 20; modernbert then qwen_embedding preference;
2,048-row train bank, ten neighbors, 128-query batches; eight clusters from
at most 2,048 training rows, 50 iterations; one alternate seed for training-only
stability; train p90 neighbor similarity and p05 cluster-outlier cutoffs.
All definitions and train-only fits are frozen before test slice evaluation.

### Validation

Commands executed locally, never submitted to SLURM:

```bash
cd /Users/yakovelmaleh/code/Master-diagnose-t5-characteristics
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python3 -W error::RuntimeWarning -m unittest discover \
  -s Tasks/diagnose-instability-models/tests -p 'test_*.py' -v
bash Tasks/run_cluster_task.sh diagnose-instability-models \
  --stage milestone2 \
  --source-run "$HOME/master-hf/diagnostics/diag-m1-20261109-02" \
  --run-id diag-m2-20261111-01 --partition main --dry-run
git diff --check
```

The 32-test suite covers old M1/review behavior plus training-only cutpoints,
literal flags, duplicate/self exclusion, existing metric/support invariants,
label-independent grouping/bank selection, repeatability/stability, cache
provenance/order/content rejection, absent test embeddings, independent T5
completion with no embeddings, M1/CI hash gates, preservation/write-once outputs,
bounded configurations and a dependency-free launcher under `python3 -S`.
Generated shell syntax is checked with `bash -n`; runtime warnings are treated
as errors. No dependencies were installed. Fixture outputs were temporary.

### Next user-operated command

**Deployment remains pending; PRs/pushes are not authorized.** No PR/push or
patch-transfer workflow was used. The coordinator must arrange authorized
deployment of these task changes before the cluster can recognize this new
stage. `git pull` alone cannot retrieve unpublished implementation.

After deployment, the user alone runs:

```bash
bash "$HOME/Master/Tasks/run_cluster_task.sh" diagnose-instability-models \
  --stage milestone2 \
  --source-run "$HOME/master-hf/diagnostics/diag-m1-20261109-02" \
  --batch-id human-review-01 \
  --run-id diag-m2-20261111-01 \
  --partition main \
  --output-root "$HOME/master-hf/diagnostics"
```

One CPU SLURM job, four CPUs/16 GB/two hours by default, existing concurrency
guard and email notifications. Printed `.out`/`.err` and job mapping live under
`Tasks/diagnose-instability-models/cluster_runs/<submission-id>/`.
The original source run remains read-only. Planned new output:
`/home/yakovelm/master-hf/diagnostics/diag-m2-20261111-01/`.

Read `summary.json` and the separate text/embedding statuses first.
Exit 2 can mean T5 text succeeded but test embedding work is unavailable.
Use `complexity/length_evidence.json`, `complexity/matched_characteristic_metrics.json`,
`complexity/exact_duplicate_disagreement.json`, `shift/temporal_shift.json`
and available `semantic-groups/` artifacts for the eventual 3-5 findings.
Each finding needs project/K, rows/positives, scores/differences, uncertainty,
configuration and limitations. Do not interpret unsupported cells as wins.

### Copyable coordination handoff

T5-first/T4 tools implemented in Master-diagnose-t5-characteristics on branch
user/yakovelmaleh/diagnose-t5-characteristics. Real analyses are NOT executed;
successful M1/CI inputs and frozen vector caches remain cluster-only. New-run
worker verifies them, freezes train-only definitions, preserves all M1 outputs,
and runs new length/empty/repetition/reference/duplicate/shift diagnostics.
Compatible cached vectors enable bounded training-bank disagreement and
label-blind grouping for available partitions only; missing test caches block
only dependent work. No new substantive findings yet. Histories remain absent,
labels unverified, and the 20 text reviews are hypothesis-generating only.
32 tests pass; no model training/inference/downloads/GPU, PR/push, notifications
or T6/T7. Deployment authorization and user-operated SLURM execution are next.

## T2/T3 review follow-up, November 11, 2026

**Current request status:** review/reconciliation exporter implemented and
validated locally; the actual approximately 20-story batch and exact-input
CI replays are **pending user-operated cluster execution**, not completed
analyses. Source run:
`/home/yakovelm/master-hf/diagnostics/diag-m1-20261109-02/`.
User-supplied results establish that this run completed T1/T2/T3 automation;
the older local-only status below is retained as historical evidence.

Worktree: `/Users/yakovelmaleh/code/Master-diagnose-review-batch`.
Branch: `user/yakovelmaleh/diagnose-review-batch`, based on `8aeebc7`.
The user authorized feature-branch PR publication for this follow-up.
Original dirty checkout untouched; no Teams notification, cluster
connection/submission, training or T4-T7 work. No story/model artifacts
are included in the PR.

Changed within this task: `scripts/prepare_review.py`,
`scripts/reconcile_intervals.py`, `scripts/diagnostic_config.py`,
`cluster/submit_jobs.py`, `tests/test_review.py`, `README.md`, `HANDOFF.md`.

The supplement requests five unique stories in each of four explicit
ranking categories, balancing projects/K/SLM1-SLM2/labels deterministically.
All original text stays outside Git. The score-disclosed diagnostic sample
does not estimate population error rates; all human answers remain blank.
Missing histories explicitly make label verification unavailable.

### Existing interval evidence, not a completed exact-input replay

Original values are from
`../sprint-data-analysis-summary/data/hf-20261019-report.json`; diagnostic
values were previously supplied from T3. The exporter must reproduce both
on the requested run's exact artifacts before reconciliation is complete.

| SLM2 cell | Test n / positives | Delta AUC-PRC | Original paired-IID 95% CI | Previously reported diagnostic time-block 95% CI |
|---|---:|---:|---|---|
| MariaDB K=15 | 398 / 33 | +0.0551590111 | [-0.0424117124, +0.1568824135] | [+0.0031760960, +0.1296754246] |
| IntelDAOS K=5 | 334 / 32 | +0.1343786104 | [+0.0045889405, +0.2767080153] | [-0.0359532116, +0.2820542318] |

Original experiment config digest
`2bc94a1680d72c09dc8a1a93e4f0806cc6e558c7ad21cdf328626690c7b33440`
matches both original report cells: seed 7, 2,000 paired IID issue draws.
The diagnostic config uses seed 20261109, 500 paired non-circular
chronological block draws, block size 20. Both use percentile limits and
skip one-class draws; neither interval adjusts for multiple comparisons or
model selection. The sampling distribution and finite-draw configuration
both differ. Block sampling need not yield wider intervals. Fixed-threshold
classification differences cannot explain ranking-metric interval changes.
The original IntelDAOS AP difference interval includes zero, unlike its
AUC-PRC interval; keep these metrics separate.

The controlled replay checks hashes, original row order, labels,
model/comparator selection, probability direction, point metrics and CSV
representation, then shows both intervals plus a fixed configuration
bridge. Neither interval is selected based on its sign. A failed replay
stays blocked. The cluster-only source prediction files are the remaining
execution input; raw histories and human answers are separately missing.

### Validation and next user action

Executed locally in the isolated worktree:

```bash
python3 -m unittest discover -s Tasks/diagnose-instability-models/tests -p 'test_*.py' -v
bash Tasks/run_cluster_task.sh diagnose-instability-models \
  --stage review --run-id diag-m1-20261109-02 \
  --batch-id human-review-01 --partition main --dry-run
git diff --check
```

**23 tests passed**, including repeatable 20-unique-story selection,
four-category coverage, multiple projects/K/families, integrity rejection,
pending blank answers, escaped full text, missing/actual history,
write-once/source preservation, exact native-input reconciliation and
both bootstrap replays. The review launcher also passes under
`python3 -S`; its generated script passes `bash -n`. No new dependencies
were installed. Fixture outputs were temporary and are not real stories
or executed cluster analyses.

Deploy through the follow-up PR, not by transferring or applying a patch.
**After the PR is merged**, update the cluster checkout:

```bash
git -C "$HOME/Master" switch main &&
git -C "$HOME/Master" pull --ff-only origin main
```

If Git reports conflicting local changes or a non-fast-forward branch,
stop and reconcile them rather than resetting or overwriting anything.
After the update succeeds, the user alone runs:

```bash
bash "$HOME/Master/Tasks/run_cluster_task.sh" diagnose-instability-models \
  --stage review --run-id diag-m1-20261109-02 \
  --batch-id human-review-01 --partition main \
  --output-root "$HOME/master-hf/diagnostics"
```

Planned output directory (not yet generated on the cluster):
`/home/yakovelm/master-hf/diagnostics/diag-m1-20261109-02/error-analysis/human-review-01/`.
Review `review_batch.html`, answer a copy of `review_sheet.csv`, and return
`ci_reconciliation.{md,json}`, `selection_manifest.json`, `status.json`
and `coordination_handoff.md` to the coordination session. Keep raw stories
local/outside Git. Existing concurrency limits, email and job/log manifests
remain in effect. Do not start T4-T7.

## User-authorized PR packaging update

After the implementation handoff, the user requested a PR. Packaging uses the
isolated worktree `/Users/yakovelmaleh/code/Master-diagnose-instability-m1`,
branch `user/yakovelmaleh/diagnose-instability-m1`, based on refreshed
`origin/main` at `277ba2c`. Only the 13 task files are included; the original
dirty checkout remains untouched. All 14 focused tests and launcher syntax
checks passed again in that clean-base worktree. A second full local run at
`/Users/yakovelmaleh/master-hf/diagnostics/m1-pr-20261109/` reproduced the same
24 verified classical cells, 522 review stories and blocked neural comparisons
(expected exit 2). The investigation evidence and incomplete-analysis status
below are unchanged. No cluster submission or Teams notification is authorized.

## Status on November 9, 2026

| Task | Implementation | Actual execution / remaining work |
|---|---|---|
| T1 | Implemented and tested | Six datasets and 24 classical cells verified locally. **Blocked** for 72 neural cells: matching sealed studies and row predictions unavailable in the searched local root. |
| T2 | Implemented and tested | Population profiles executed; 522 deduplicated stories prepared. **Pending human review**; source histories and model-specific per-row truncation unavailable locally. Label validity is not established by formula agreement. |
| T3 | Implemented and tested | 38,128 classical validation/test diagnostic rows written. **Blocked** for cross-family comparisons; zero matched neural comparisons executed. Review candidates are not a reviewed example set. |

During implementation, no T4-T7 work, training, relabeling, presentation edits, external uploads,
cluster access/submission, commits, pushes, PRs or Teams notifications occurred.
Existing splits, labels, experiments and unrelated checkout changes were left
unchanged.

## Checkout and files

Repository: `/Users/yakovelmaleh/code/Master`.
Branch unchanged: `user/yakovelmaleh/code-smell-prediction`.
No separate worktree was used during implementation; PR packaging now uses
the isolated worktree above. Every implementation/documentation change is
confined to the initially untracked `Tasks/diagnose-instability-models/`.
No files were staged during the investigation.

Changed/added relative to the starting task:

```text
README.md
HANDOFF.md
.gitignore
configuration/milestone1.json
scripts/support.py
scripts/evidence.py
scripts/data_profile.py
scripts/token_coverage.py
scripts/errors.py
scripts/run_diagnostics.py
cluster/submit_jobs.sh
cluster/submit_jobs.py
tests/test_milestone1.py
```

`Tasks/run_cluster_task.sh` needed no edits: it discovers the new launcher.
Submission uses one CPU array element, the existing global HF lock/active-job
guard, explicit stdout/stderr, stage/job mapping and existing email defaults.

## Persistent artifacts and evidence

**Final executed run:**
`/Users/yakovelmaleh/master-hf/diagnostics/m1-local-20261109-v3/`.
Its recorded source fingerprint was checked against the final implementation.
Earlier local smoke runs `m1-local-20261109-v1` and `-v2` remain outside Git and
are superseded; use **v3** for this handoff.

The final run contains:

```text
run.json
manifest/artifact_manifest.json
manifest/comparison_contract.json
manifest/integrity_checks.json
manifest/{inventory,profile,errors}_status.json
manifest/{population,predictions}.csv
data-characterization/data_profile.json
data-characterization/characteristics.csv
data-characterization/token_coverage.{csv,json}
data-characterization/sampling_plan.json
data-characterization/label_audit.csv
data-characterization/review_examples.jsonl
data-characterization/summary.txt
error-analysis/row_diagnostics.csv
error-analysis/error_slices.json
error-analysis/review_candidates.csv
```

CSV hash/provenance sidecars accompany the CSVs. Do not copy row-level files,
raw story packets, annotations or checkpoints into Git.

Supported observations:

- All six source hashes, frozen chronological partitions, row/label hashes,
  binary/nested labels and implemented count-rule labels reconciled:
  **23,822 eligible stories**, with 79 rows excluded by the unchanged loader.
  No label-construction count was missing in the eligible population.
- The archived six-candidate classical pool was rechecked per project/K.
  All **24 validation-selected classical cells** reproduced AUC-PRC, AP,
  ROC AUC, counts and fixed thresholds on **48 validation/test partitions**.
  Twenty-four archived selected model blobs were inventoried by Git identity
  and size, not deserialized or retrained.
- All K share **4,770 test stories**; positive counts at K=5/10/15/20 are
  **747 / 557 / 463 / 296**. Do not add these nested positives as independent
  observations.
- **23,822/23,822** eligible rows have empty acceptance-criteria text after the
  existing preprocessing; **5,686** have empty description text. This is a
  data-availability observation, not proof of an extraction error or a cause
  of model performance.
- There are **556 normalized-text duplicate rows**, including **215 rows**
  whose normalized text appears in more than one split. Counts are rows, not
  duplicate groups. The bounded near-duplicate screen is not exhaustive.
- The frozen review plan has **288 strata**, **522 unique sampled stories**
  and **109 assigned to independent second review**. **Zero human reviews**
  were performed. Histories and language classification remain unavailable.
- Aggregate-report arithmetic recovers **11/24 SLM1, 11/24 SLM2, 1/24 Jev**
  AUC-PRC wins. These are **not neural prediction reproductions or significance
  claims**. T1 verifies only 24/96 family/project/K cells locally.
- No matching neural study was found in the explicitly searched local
  `$HOME/master-hf` root. This is not a claim that cluster artifacts are absent.
  T3 records 48 blocked project/split/K groups and zero cross-family comparisons.

Source-code tracing also found that the extractor's word counters compare
first eligible post-entry `from_string` with exported last text; the inspected
function does not impose a sprint-end bound. Sprint-entry construction has
sprint-start/change-time/issue-created fallbacks. These are **code observations**,
not per-row history verification; keep the original targets unchanged.

## Commands run and validation

```bash
cd /Users/yakovelmaleh/code/Master
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s Tasks/diagnose-instability-models/tests -v
bash -n Tasks/diagnose-instability-models/cluster/submit_jobs.sh
bash Tasks/run_cluster_task.sh diagnose-instability-models \
  --stage inventory --run-id launcher-check --partition main --dry-run | bash -n
git diff --check
PYTHONDONTWRITEBYTECODE=1 python3 \
  Tasks/diagnose-instability-models/scripts/run_diagnostics.py \
  --stage milestone1 --run-id m1-local-20261109-v3 \
  --output-root "$HOME/master-hf/diagnostics"
```

**14 focused tests passed.** Shell syntax, Python AST checks and task-local
whitespace checks passed, including untracked files. The final bounded local
run persisted its outputs and exited **2 as designed**: inventory blocked,
profile computation succeeded, errors blocked. Human label review remains
pending despite successful profile computation. There is no existing
repository-wide lint configuration for these task scripts.

Unit tests mock `squeue`/`sbatch`; their printed job `12345` is a fixture, **not
a real submission**. Actual launcher validation used `--dry-run` only.

## Missing inputs and next user action

The user/coordinator must first synchronize **only this task directory** to
the cluster checkout at `$HOME/Master/Tasks/diagnose-instability-models/`.
No automatic pull or push is part of this handoff.

Then the next user-operated cluster command is:

```bash
bash "$HOME/Master/Tasks/run_cluster_task.sh" diagnose-instability-models \
  --stage inventory --run-id diag-m1-20261109-01 --partition main \
  --artifact-root "$HOME/master-hf" \
  --output-root "$HOME/master-hf/diagnostics"
```

Use the site's CPU partition if it is not `main`. The environment defaults to
the existing `master-hf`. If original studies are elsewhere, pass their
external roots with repeated `--artifact-root` under a **new run ID**.
The inventory manifest identifies required study digests, matching roots and
missing selected artifacts. Needed inputs are original `study.json`,
`sealed.json`, final and selected-validation predictions/metrics, inference
metadata, and optional source histories plus pinned tokenizer cache.

After inventory finishes, inspect:
`$HOME/master-hf/diagnostics/diag-m1-20261109-01/manifest/integrity_checks.json`.
Per-submission `job_manifest.json` maps stages to job IDs. Logs are:
`$HOME/Master/Tasks/diagnose-instability-models/cluster_runs/<submission-id>/logs/slurm-<job-id>_0.{out,err}`.
README section 11 gives subsequent profile/errors commands and the normalized
history/review contracts. Do not advance to later milestones.

## Copyable coordination handoff

```text
MAster SLM: milestone-1 tools only are implemented under Tasks/diagnose-instability-models.
Branch untouched: user/yakovelmaleh/code-smell-prediction; no commits/push/PR/cluster submission.
14 tests + dispatcher dry-run/shell/Python/whitespace checks passed.
Final local evidence: /Users/yakovelmaleh/master-hf/diagnostics/m1-local-20261109-v3/.
T1: 6 datasets / 23,822 stories verified; 24 classical cells reproduced on validation+test.
72 neural cells blocked: sealed SLM1/SLM2/Jev studies and row predictions unavailable locally.
T2: profiles executed; 522 unique review stories, 109 double-review assignments; 0 human reviews.
All acceptance text empty; 5,686 descriptions empty. These are observations, not causal findings.
T3: 38,128 classical row diagnostics; 0 cross-family comparisons; blocked pending cluster evidence.
11/24, 11/24, 1/24 wins recovered from aggregate arithmetic only, not neural score reproduction.
User must sync this task directory, then run the inventory command in HANDOFF.md/README section 11.
Stop here: do not mark T1-T3 analyses complete or start T4-T7.
```
