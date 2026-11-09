# Milestone 1 handoff to MAster SLM

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
