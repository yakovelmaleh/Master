# Diagnosing unstable-user-story prediction

**Status: milestone 1 tools implemented; investigation not complete.** T1-T3
have CPU-only analysis tools, focused tests and a SLURM launcher. Local execution
has verified the frozen datasets and archived classical predictions; missing
neural row artifacts and source histories block the remaining comparisons and
label validation. Human review is pending. No new training, label changes,
model improvements or T4-T7 implementation has been performed. See section 11
for execution, limitations and the coordination handoff.

## 1. What we want to understand

We expected pretrained language models to improve on the existing classical
models when predicting unstable user stories. The completed experiments did not
show consistent improvement.

This investigation answers three questions:

1. **Why do the models make mistakes?**
2. **What are the characteristics of the labeled user stories?**
3. **Which changes could improve prediction, and how will we test them?**

We will diagnose before training more models. The goal is not to produce many
plots or to assume a larger model will solve the problem. Each analysis must
connect an observation to evidence, a possible explanation, and a testable action.

## 2. What "unstable" means in this task

We predict **future user-story text instability**, using information available
at sprint entry. The text fields are summary, description, and acceptance
criteria.

The existing dataset has four separate binary targets:
**K = 5, 10, 15, and 20 changed words**. These are word counts, not percentages.
For each K, the implemented label is:

```text
unstable_at_K =
    num_different_words_all_text_sprint >= K
    AND num_changes_summary_description_acceptance_sprint > 0
```

For example, a story with a qualifying change and a recorded changed-word count
of 12 has the following labels:

| Target | Label |
|---|---|
| K = 5 | Unstable (1) |
| K = 10 | Unstable (1) |
| K = 15 | Stable at this threshold (0) |
| K = 20 | Stable at this threshold (0) |

These are **nested targets**, not four disjoint groups of stories. A story may
be positive at several thresholds. Stable at K does not necessarily mean that
the story never changed; its change may simply fall below K.

We will preserve this definition throughout the initial investigation. We will
also trace how the changed-word count and observation period were constructed,
and examine whether recorded changes represent requirement changes, editorial
changes, or other edits. A correct label under the current rule is not a
mislabeled row merely because its edit is editorial.

Any proposed alternative target belongs to a separately approved experiment.
It must not silently replace the existing labels.

## 3. Starting evidence and comparison rule

The existing studies use Apache, Hyperledger, IntelDAOS, Jira, MariaDB, and Qt.
Each project has its own chronological 60% training / 20% validation / 20% test
split. Six projects and four K values give **24 comparisons per study**.

| Study | Models | Higher test AUC-PRC than validation-selected classical |
|---|---|---:|
| SLM1 | ModernBERT and Qwen embeddings | 11/24 |
| SLM2 | Phi, Gemma, and Qwen3.5 | 11/24 |
| Local Jev | Community DeBERTa Jev-style native classifier | 1/24 |

These counts come from the saved reports, not a new experiment. The classical
pool includes RF, legacy boosting (artifact label `XGboost`), and NN, with
baseline/refactored variants. The local Jev experiment uses a different,
zero-shot protocol; it is not official TypeSafe Jev.

**Primary rule: higher AUC-PRC means better on our comparison metric.**

- Compare the same project, K, rows, and labels.
- Compute wins from unrounded `auc_prc` values.
- Use the classical candidate selected on validation for the main comparison.
- Keep any best-observed-test comparison explicitly retrospective and separate.
- Retain AP, prevalence, ROC AUC, and other diagnostics in JSON. Do not call an
  AP win an AUC-PRC win.
- A numerical win is not automatically a statistically significant improvement.
- AUC-PRC above 0.5 alone is not sufficient evidence of useful prediction:
  the existing constant-score control can also exceed 0.5 with trapezoidal
  integration. Preserve these controls, even when slides focus on AUC-PRC.

The problem is therefore **inconsistent improvement**, not failure on every
project and threshold.

## 4. Hypotheses, not conclusions

| Possible explanation | Evidence we would look for |
|---|---|
| Original text contains limited information about future edits | Similar original stories have different outcomes; available pre-sprint metadata helps more than text |
| Labels capture several different kinds of change | Manual inspection finds different edit categories with different error rates |
| Some labels or observation histories are unreliable | Reconstructed histories disagree with stored labels, or follow-up coverage differs |
| Important information is missing or truncated | Errors concentrate in missing fields or truncated stories |
| Positive examples are sparse or not representative | Low positive support, high variation across samples, or learning curves that improve with more examples |
| Newer stories differ from training stories | Changes over time in text, labels, metadata, or semantic groups |
| Classical models use useful signals that the SLM does not | Controlled text-only and structured-feature comparisons expose the difference |
| Training, representation, or selection is unsuitable | Validation diagnostics, repeated seeds, or training dynamics reveal specific weaknesses |

No single plot proves one of these explanations. In particular, poor semantic
separation does not prove that the target is impossible to predict.

## 5. Tasks and execution order

The **completion criteria below remain pending**. T1-T3 tools and partial local
artifacts now exist (section 11); implementation is not completion of analysis.
T4-T7 remain unimplemented and outside the first milestone.

### T1. Establish the evidence and comparison contract

**Question:** Can we trust and align the inputs to the investigation?

Work:

- Inventory frozen datasets, reports, selected checkpoints, predictions, token
  coverage reports, and available issue histories.
- Verify source hashes, row identities, splits, labels, and model identities.
- Join predictions by project and row identity, not incidental CSV order.
- Check probability direction, feature timing, and label nesting across K.
- Recompute reported AUC-PRC from saved predictions and reconcile discrepancies
  before interpreting results.
- Inventory input features and training/selection differences between classical,
  SLM, and Jev protocols. Do not assume their inputs or training budgets match.
- Record missing artifacts. Aggregate reports alone cannot support row-level
  error analysis, label review, or Data Maps.

**Outputs:** `artifact_manifest.json`, `comparison_contract.json`,
`integrity_checks.json`.

**Done when:** Every available comparison is aligned and reproducible; missing
or invalid inputs are explicitly excluded or marked blocked.

### T2. Characterize the data and audit the labels

**Depends on:** T1.

**Question:** What distinguishes stable and unstable stories at each K?

Work:

- Summarize counts and prevalence by project, split, K, and time period.
- Examine text lengths, missing fields, language, templates, code/log content,
  duplicate or near-duplicate text, and model-specific token truncation.
- Examine changed-word counts, especially near 5, 10, 15, and 20.
- Check the construction of sprint-entry snapshots and the available
  post-entry observation window. Do not assume missing history means stability.
- Define a review rubric and sample size before reviewing examples.
- Review a stratified sample across projects, K, classes, and boundary cases.
  Deduplicate stories shared across K and keep sampling probabilities/counts.
- Where histories exist, classify edits such as substantive requirement changes,
  clarification, formatting, copied logs, and mixed/unclear changes.
- Keep reviewers blind to model scores where practical; independently review a
  subset and record disagreements.
- Distinguish extraction errors, uncertain histories, and valid-but-editorial
  labels. Do not automatically delete or relabel difficult examples.

**Outputs:** `data_profile.json`, `label_audit.csv`, a concise data summary.

**Done when:** We can describe the population and label meaning, quantify
available support, and identify audit findings with representative evidence.
If source histories are unavailable, label validity remains unverified.

### T3. Compare model errors on the same stories

**Depends on:** T1. Can run alongside T2; incorporate its findings afterward.

**Question:** Where does classical prediction outperform the SLM, and vice versa?

Work:

- Compare classical, SLM1, SLM2, and Jev predictions on matched stories.
- Inspect unstable stories ranked too low and stable stories ranked too high.
  Ranking errors are central because AUC-PRC is our primary metric.
- Also inspect false positives and false negatives at the already fixed,
  validation-selected thresholds; report these separately from ranking quality.
- Separate shared mistakes from disagreements: classical succeeds / SLM fails,
  SLM succeeds / classical fails, and both fail.
- Relate errors to length, missing fields, truncation, time, and audited edit type.
- Include matched successes as controls, not only memorable failure examples.
- Report sample sizes, positive counts, and uncertainty. Small or one-class
  slices cannot support reliable AUC-PRC comparisons.

**Outputs:** `row_diagnostics.csv`, `error_slices.json`, a reviewed example set.

**Done when:** The main error patterns have quantified support and examples,
without claiming that correlation establishes the cause.

### T4. Discover and inspect semantic groups

**Depends on:** T2 and T3.

**Question:** Are particular types of stories associated with poor predictions?

Work:

- Prefer reusable frozen embeddings where their provenance is suitable.
  Record the encoder, revision, input fields, and truncation policy.
- Build label-blind semantic groups using training text only; choose analysis
  settings without optimizing test scores.
- Assign validation/test stories using the frozen grouping procedure, with an
  explicit policy for outliers or stories unlike training examples.
- Inspect representative stories and manually name groups only after review.
- For each group, show support, class mix at each K, and matched model results.
- Check whether groups mostly reflect project, language, text length, or repeated
  templates rather than meaningful requirement categories.
- Check robustness to reasonable clustering settings. A two-dimensional plot
  is an illustration, not evidence that classes are separable.

**Outputs:** `cluster_assignments.csv`, `cluster_profiles.json`, representative
examples and a small set of useful visualizations.

**Done when:** Groups are interpretable and sufficiently supported, or we record
that clustering did not reveal a stable, useful structure.

### T5. Measure data complexity and temporal shift

**Depends on:** T2 and T3. May proceed alongside T4.

**Question:** Is the available prediction problem sparse, overlapping, or changing?

Work:

- Examine near-neighbor label disagreement and class overlap in a documented
  feature space. Treat these as representation-dependent diagnostics.
- Quantify train/validation/test differences in prevalence, text characteristics,
  metadata, and embedding distributions.
- Compare existing text-only and combined-feature validation results first.
- Identify gaps requiring controlled text-only, structured-only, and combined
  experiments; these are new runs requiring separate approval.
- Design learning curves and repeated-seed checks if needed. Fit preprocessing
  on training data only and evaluate development choices on validation data.

**Outputs:** `complexity_profile.json`, `shift_report.json`, and, if approved,
learning-curve and feature-ablation results.

**Done when:** We have evidence for or against the main complexity hypotheses,
with untested explanations clearly distinguished from measured findings.

### T6. Use Data Maps if training dynamics can answer a remaining question

**Depends on:** T2 and T3, plus approval for a separate diagnostic training run.

**Question:** Which examples are consistently learned, uncertain, or difficult?

The current adapter training loop saves the final model/head, but does not log
per-example probabilities across epochs. Final predictions are not sufficient
to reconstruct a Data Map. This stage is therefore conditional, not a required
first step.

Work, if approved:

- Choose a bounded representative SLM configuration and project/K scope based
  on development evidence and available compute.
- Record true-label probability and correctness for each training example at
  fixed evaluation checkpoints, using a consistent evaluation mode.
- Derive mean confidence, variability, and correctness across checkpoints.
- Relate map regions to label review and error slices.
- Keep this model-dependent diagnostic separate from frozen-head and zero-shot
  Jev results, which do not have equivalent training dynamics.
- Review difficult examples; do not assume they are mislabeled.

**Outputs:** `training_dynamics.jsonl`, `data_map.csv`, reviewed region summaries.

**Done when:** Dynamics are complete and traceable and support a specific
diagnostic conclusion, or this stage is explicitly deferred as unnecessary.

### T7. Turn findings into a small improvement plan

**Depends on:** T2-T5 and a documented completion/defer decision for T6.

**Question:** What should we change, and what would demonstrate that it helped?

Use the following format for each proposed experiment:

| Field | Required content |
|---|---|
| Finding | What we observed, including affected projects/K and support |
| Evidence | Artifact paths, example references, effect size, uncertainty |
| Explanation | Plausible mechanism and competing explanations |
| Proposed change | One primary change, not a bundle of unrelated modifications |
| Test | Baseline, fixed split, metric, compute budget, and acceptance rule |
| Outcome | Supported, rejected, or inconclusive after the approved experiment |

Examples, not preselected fixes:

- Truncation evidence -> field-aware encoding or additional context.
- Useful structured signals -> controlled text-plus-metadata experiment.
- Insufficient representative positives -> additional historical training data.
- Training instability -> bounded optimization and repeated-seed experiment.
- Unreliable extraction -> corrected data pipeline and a separately versioned
  dataset, preserving the original study.
- Target mixes distinct phenomena -> separately approved target-definition study.

**Outputs:** `findings.json`, `improvement_plan.md`, and a short human-readable
summary of what we know, what remains uncertain, and what to test next.

**Done when:** Each prioritized change has evidence and a falsifiable evaluation
plan. It is acceptable to conclude that more or different information is needed.
Executing improvement experiments is a later approval step, not completion of
this documentation task.

## 6. Evaluation safeguards

- Preserve original datasets, labels, sealed choices, predictions, and reports.
- Existing test results have already been observed. Analysis of those rows is
  exploratory, not a new independent confirmation.
- Develop decisions on training/validation data. Do not select prompts,
  thresholds, clusters, seeds, or models to maximize the observed test result.
- Confirm subsequent improvements on a fresh, unseen chronological holdout.
  If none is available, state that confirmation is pending.
- Use paired comparisons on matched rows. Account for time dependence and
  repeated stories where feasible, and declare the uncertainty method.
- Do not treat the same story at four K values as four independent examples.
- Check support before interpreting slice scores; report undefined metrics.
- Distinguish exploratory slice discovery from confirmatory testing and account
  for multiple comparisons when making significance claims.
- Future edits may be inspected for label auditing, but must never become
  prediction-time features.
- Do not send story text or model artifacts to external APIs without explicit
  approval. Keep row-level diagnostics and checkpoints outside Git.

## 7. Repository, cluster, and output organization

### Contents now

```text
Tasks/diagnose-instability-models/
  README.md
  .gitignore                # Task-local runtime / row-artifact safeguards
  configuration/milestone1.json
  scripts/
    support.py              # Shared frozen contracts and external-only outputs
    diagnostic_config.py    # Dependency-free submission/runtime validation
    evidence.py             # T1 inventory, provenance, exact alignment, metrics
    data_profile.py         # T2 population profiles and blinded review packets
    token_coverage.py       # Optional pinned offline tokenizer-only coverage
    errors.py               # T3 matched ranking / fixed-threshold diagnostics
    run_diagnostics.py      # Only inventory/profile/errors/milestone1 stages
  cluster/submit_jobs.{sh,py}
  tests/test_milestone1.py
  cluster_runs/<submission-id>/logs/  # Ignored; created on user submission
```

### Reserved organization

Later-stage directories are reserved, not implemented or authorized:

```text
Tasks/diagnose-instability-models/
  README.md
  configuration/            # Frozen analysis choices and sampling rules
  scripts/                  # Analysis stages
  cluster/                  # SLURM submission and stage mapping
  tests/                    # Label, alignment, metric and leakage checks
  summaries/<run-id>/        # Reviewed aggregate outputs only
  cluster_runs/<submission-id>/logs/  # Local ignored .out/.err logs
```

Full results should be stored outside Git, proposed as:

```text
$HOME/master-hf/diagnostics/<run-id>/
  manifest/
  data-characterization/
  error-analysis/
  semantic-clustering/
  data-complexity/
  data-maps/                # Only if T6 runs
  synthesis/
```

Every artifact should identify its diagnostic run, stage, source study,
project/K scope, source/configuration hashes, and metric definitions.
Record an explicit stage status: succeeded, failed, blocked, or deferred.

The launcher now integrates with `Tasks/run_cluster_task.sh` through its
existing automatic discovery of `cluster/submit_jobs.sh`. Each submission writes
`job_manifest.json`, a frozen configuration, and `submit.sbatch`, plus separate
`.out`/`.err` logs. One CPU job runs at a time (`0-0%1`); the launcher shares the
existing global HF submission lock and refuses submission while another
`master-hf-*` job is active. Email uses the existing default recipient and
`--mail-type=ALL`. Long-running work must use SLURM. **The user submits jobs;
the assistant never SSHs or submits jobs.** Verified commands are in section 11.

CPU-only artifact analysis comes first. New embeddings, learning curves,
controlled ablations, and Data Maps may require additional compute. Approve
their scope and budget before submitting them.

## 8. Presentation and final handoff

Keep the presentation focused:

1. What we investigated.
2. The most important data characteristics and error patterns.
3. What the evidence supports, and what it does not.
4. Which improvement experiment comes next and why.

Use AUC-PRC for visible model comparisons. Keep AP, detailed diagnostics,
methodological caveats, and full tables in JSON/reports or speaker notes.
Use the appropriate sprint's existing template-based presentation; choose the
sprint before adding slides. Do not overwrite or reorder the user's existing
slides as part of this investigation.

## 9. Task checklist

- [ ] T1: Verify artifacts, alignment, and comparison contract.
- [ ] T2: Characterize data and audit labels.
- [ ] T3: Analyze matched model errors.
- [ ] T4: Discover and inspect semantic groups.
- [ ] T5: Measure data complexity and temporal shift.
- [ ] T6: Run approved Data Maps analysis, or document why it is deferred.
- [ ] T7: Synthesize findings and prioritize controlled improvements.

**First implementation milestone:** T1-T3, using existing artifacts before
requesting new model training.

## 10. Evidence and methodology references

Repository evidence:

- Label definition:
  `Using_CSV_files/Load_Data_From_Jira_To_CSV/ChooseFeaturesColumns.py`,
  relative to the repository root.
- Frozen population and baseline contract:
  `../train-hf-instability-within-project/reference_contract.json` and
  `../train-hf-instability-within-project/data_contract.py`.
- Training implementation:
  `../train-hf-instability-within-project/model_adapters.py`.
- SLM reports:
  `../sprint-data-analysis-summary/data/hf-20261008-report.json` and
  `../sprint-data-analysis-summary/data/hf-20261019-report.json`.
- Jev report:
  `../sprint-data-analysis-summary/data/jev-20261029-report.json`.
- Both classical comparison definitions:
  `../sprint-data-analysis-summary/data/classical-best-comparison-20261029.json`.

The report JSONs contain aggregate metrics and provenance, not all the
row-level evidence needed for this investigation. T1 must locate the actual
cluster artifacts rather than assume that the repository contains them.

Methodology background:

- *Dataset Cartography: Mapping and Diagnosing Datasets with Training Dynamics*
  (Swayamdipta et al., 2020), arXiv:2009.10795.
- *Domino: Discovering Systematic Errors with Cross-Modal Embeddings*
  (Eyuboglu et al., 2022), arXiv:2203.14960. Background for coherent error-slice
  discovery; not a commitment to use that implementation.

## 11. Milestone 1 operation and handoff

### Execution contract

Run on the cluster only after the user/coordinator synchronizes this task
directory to `$HOME/Master/Tasks/diagnose-instability-models/`. The investigation
phase did not publish code or submit jobs; the user subsequently authorized PR
publication (see `HANDOFF.md`). Cluster synchronization/submission remains
user-operated. The submission launcher uses only the Python standard library:
NumPy/pandas need not be installed in the login-node Python, and configuration
is validated before submission without importing the analysis runner.
The generated SLURM script activates the existing `master-hf` environment,
which supplies NumPy and pandas for analysis; inventory and
matched-score analysis do not require scikit-learn, torch, model inference or
network access. Optional tokenizer coverage uses the already installed
Transformers and an existing pinned local cache. No dependency installation,
model download or model training is performed.

**Next user-operated command:**

```bash
bash "$HOME/Master/Tasks/run_cluster_task.sh" diagnose-instability-models \
  --stage inventory --run-id diag-m1-20261109-01 --partition main \
  --artifact-root "$HOME/master-hf" \
  --output-root "$HOME/master-hf/diagnostics"
```

`main` follows the existing Jev cluster commands; change it if the site's CPU
partition differs. `--dry-run` prints a shell-syntax-validated submission
script without creating directories or calling `squeue`/`sbatch`. The launcher
was tested through the actual dispatcher, not only its Python entry point.
It prints exact log and manifest paths after a user submission:

```text
$HOME/Master/Tasks/diagnose-instability-models/cluster_runs/<submission-id>/
  configuration.json
  submit.sbatch
  job_manifest.json              # T1/T2/T3 -> job ID and array index
  logs/slurm-<job-id>_0.out
  logs/slurm-<job-id>_0.err
```

Inventory searches `<artifact-root>/runs/*/study.json`,
`<artifact-root>/jev-runs/*/study.json`, and `<artifact-root>/study.json`.
Studies are identified by their original report's study digest, **not names,
directory order, model popularity or test performance**. Repeat
`--artifact-root` for another external storage root or direct study directory.
Candidate history/extractor CSV and saved token-report files are inventoried,
not silently parsed as complete histories. Root discovery is bounded to the
explicit roots; absence there does not prove artifacts never existed.

The inventory job also extracts verified populations and saved predictions
into external diagnostic CSVs; no raw-story transfer or model regeneration is
necessary. Its `artifact_manifest.json.required_studies` gives exact missing
study digests and required artifact shapes. Study and seal identities, selected
model/configuration, prediction hashes, labels, full partition identity sets,
and ranking metrics must reconcile before that cell enters T3.

Missing/invalid cells are explicitly **blocked**, not filled from aggregates,
inverted, truncated to an intersection, or replaced by another model. The
classical pool is reselected on archived validation AUC-PRC with its original
tie-break. Classical model blobs are inventoried by immutable Git object ID
and size, never unpickled. Missing HF weights are marked non-replayable; saved
score analysis can still proceed when inference metadata, seals and prediction
hashes reconcile. Missing inference metadata blocks the cell.

Exit codes: `0` = requested computational stages succeeded; `2` = available
work was saved but required comparisons are blocked; `1` = execution failed.
An expected blocked inventory therefore makes SLURM report failure while
retaining usable evidence. Read the status JSONs, not just SLURM's exit state.

After inspecting inventory, the user may run profile/error stages using the
**same run ID, roots, configuration and source version**:

```bash
bash "$HOME/Master/Tasks/run_cluster_task.sh" diagnose-instability-models \
  --stage profile --run-id diag-m1-20261109-01 --partition main \
  --artifact-root "$HOME/master-hf" \
  --output-root "$HOME/master-hf/diagnostics"

bash "$HOME/Master/Tasks/run_cluster_task.sh" diagnose-instability-models \
  --stage errors --run-id diag-m1-20261109-01 --partition main \
  --artifact-root "$HOME/master-hf" \
  --output-root "$HOME/master-hf/diagnostics"
```

Wait for each submission to finish before the next command. Alternatively,
`--stage milestone1` runs T1-T3 sequentially in one CPU job, continuing with
verified unaffected inputs when other cells are blocked. It does not execute
later milestones. Each stage is write-once: after an attempt, use a **new run
ID** for retries, changed code/configuration, restored studies or new history
inputs. This prevents overwriting human review work or mixing provenance.

Optional `--tokenizer-cache "$HOME/master-hf/cache"` and
`--histories /external/path/histories.jsonl` must be supplied consistently from
inventory onward. Token coverage verifies pinned tokenizer bytes and runs
offline without loading weights. It preserves HF special-token behavior and
Jev's no-special-token state limit. Missing token evidence remains unavailable,
not estimated from word counts. Missing/failed optional coverage is marked
blocked in `token_coverage.json` without discarding valid population profiles.

### External outputs and review

All data-bearing outputs live under:
`$HOME/master-hf/diagnostics/<run-id>/`.

| Directory | Outputs |
|---|---|
| Root | `run.json`: frozen source/configuration/input provenance |
| `manifest/` | `artifact_manifest.json`, `comparison_contract.json`, `integrity_checks.json`, stage statuses; `population.csv`, `predictions.csv` |
| `data-characterization/` | `data_profile.json`, `characteristics.csv`, `token_coverage.{csv,json}`, `sampling_plan.json`, `label_audit.csv`, `review_examples.jsonl`, `summary.txt` |
| `error-analysis/` | `row_diagnostics.csv`, `error_slices.json`, `review_candidates.csv` |

JSON artifacts carry run/stage/status/source/configuration metadata. CSV
sidecars carry hashes, columns and row counts; downstream stages verify those
hashes. These CSVs, review packets and annotations must never enter Git.
CLI output and scheduler logs do not print raw story text. Files are created
with private permissions.

Sampling is frozen before review: two stories per nonempty
project/split/K/class/boundary stratum (at most; boundary is K +/- 1 word).
The union is deduplicated across K. Every stratum records population, sample
size, selected IDs and probability; each sampled story records its union
inclusion probability. A seeded independent subset is assigned for second
review. This is a declared operational sample, not a precision-powered audit.
The complete rubric is in `sampling_plan.json`.

Give reviewers `review_examples.jsonl` and the rubric, **not model scores or
T3 diagnostics**. Annotations start `pending`; no script claims human review
occurred. Edit categories include substantive requirement, clarification,
editorial/formatting, copied logs/code, mixed, unclear and no observed edit.
Evidence quality and extraction consistency are separate judgments.

Optional normalized history JSONL has one object per `project:issue_key`:

```json
{"row_id":"Apache:EXAMPLE-1","project":"Apache","observation_start":"2020-01-01","observation_end":"2020-03-01","history_complete":false,"events":[{"field":"summary","at":"2020-02-01","before":"Old example","after":"New example"}]}
```

Use the frozen dataset's timezone convention and provide truthful observation
coverage. Events require actual string values for `before`/`after`, not
fabricated empty strings for missing evidence. Only summary, description and
acceptance_criteria are accepted. Duplicate/unknown identities, invalid
coverage and out-of-window events block history review. Packets contain real
diffs, first-observed-snapshot consistency checks and history-chain gaps.
Adjacent-edit word deltas are **not** silently substituted for the historical
first-eligible-`from_string` versus exported-last-text label counters.
No automatic semantic edit classification or relabeling occurs.

Copy `label_audit.csv` outside the run, fill the rubric/reviewer/rationale
columns, and keep independent disagreements in the second-review columns.
When first running the errors stage, add
`--reviews /external/path/completed-label-audit.csv` to ingest only explicitly
reviewed entries. Frozen sample IDs and rubric values are verified; these
slices describe sampled reviewed stories, not population error rates.

T3 separates AUC-PRC/ranking diagnostics from fixed-threshold FP/FN and
matched successes. Per-story ranking error is the fraction of opposite-class
scores inverted, counting ties as one half; equal-score rank bounds avoid
arbitrary within-tie order. Main paired differences use a seeded moving
time-block bootstrap within project/split/K (500 samples, blocks of 20 rows).
Slices require at least 50 rows, 10 positives and 10 negatives for an
interpretation; one-class ranking metrics are null. Slice intervals are not
fabricated. All intervals are exploratory/unadjusted and make no significance
claim. Nested K are never pooled as independent examples. Lexical
near-duplicate screening is bounded and approximate; language identification,
per-row truncation and audited edit type are explicitly unavailable where
evidence is absent.

### First diagnostic human-review supplement (T2/T3 only)

The score-disclosed review requested for `diag-m1-20261109-02` is a **separate
diagnostic sample**, not a replacement for the model-blind 522-story label
audit above. The exporter reads a completed existing run without reinitializing
it, changing its source fingerprint, rerunning model inference, or altering any
original outputs. It records both the original run provenance and the new
exporter's file hashes. Merge the follow-up PR and update the cluster checkout
before using this new launcher stage; no patch transfer is needed:

```bash
git -C "$HOME/Master" switch main &&
git -C "$HOME/Master" pull --ff-only origin main
```

Stop if Git reports conflicting local changes or a non-fast-forward branch;
do not reset or overwrite them. After the merged update is present, run:

```bash
bash "$HOME/Master/Tasks/run_cluster_task.sh" diagnose-instability-models \
  --stage review \
  --run-id diag-m1-20261109-02 \
  --batch-id human-review-01 \
  --partition main \
  --output-root "$HOME/master-hf/diagnostics"
```

Do not pass new artifact roots, histories, tokenizer caches or annotations:
this stage inherits the source run's evidence. It shares the existing one-job
concurrency guard, CPU resource limits, email notifications and `.out`/`.err`
layout. Its `job_manifest.json` maps the one job to T2 review preparation and
T3 interval reconciliation. `--dry-run` remains standard-library-only.

The frozen policy in `scripts/diagnostic_config.py` requests **20 unique
stories, five per category**, from full verified test partitions, using SLM1
and SLM2 versus their validation-selected classical comparator:

- Classical good / SLM poor ranking.
- SLM good / classical poor ranking.
- Both poor.
- Both good.

"Good" means at most 25% of opposite-class pairs inverted; "poor" means at
least 50%, counting ties as half. These are explicit diagnostic categories,
not absolute claims of correctness or new classifier thresholds. Inversion
uses the full project/test/K opposite-class population, never the review
sample. Recorded fixed-threshold predictions are shown separately.

Selection cycles through categories, preferring least represented project,
K, family, label and category/project, then breaking ties by seed `20261111`
and identity hash. A story may appear only once across all K/family pairs.
Candidate support, quotas, diversity and any shortfall are recorded. The
exporter never silently relaxes thresholds to obtain 20 examples. This is a
purposive diagnostic sample, **not an estimate of population error rates**.

The new write-once external directory is:

```text
/home/yakovelm/master-hf/diagnostics/diag-m1-20261109-02/error-analysis/human-review-01/
  status.json
  selection_manifest.json
  review_batch.html
  review_batch.json
  review_sheet.csv
  ci_reconciliation.json
  ci_reconciliation.md
  coordination_handoff.md
```

Open the HTML locally; it contains the full original text, K/label, scores,
tied ranks, inversion explanations, and real later edits/timestamps **only
where validated histories exist**. Story text is escaped and the page makes
no network requests. Scores are initially collapsed to encourage text-first
inspection, but this is explicitly **not blinded review**. Missing histories
make label verification unavailable; they never imply no changes occurred.
Actual edit evidence still requires human interpretation and does not
automatically reproduce the historical count rule.

Copy `review_sheet.csv` outside the write-once batch before answering. All
answers/reviewer fields are blank and all review statuses are `pending`.
This sheet belongs to the new diagnostic sample; it is **not compatible with**
the original frozen `label_audit.csv` ingestion via `--reviews`. Do not
relabel records or count any reviews as complete before human answers exist.
All these artifacts, including the answer sheet, must remain outside Git.

The interval reconciliation is restricted to SLM2 MariaDB K=15 and
IntelDAOS K=5. It checks the original report/study/selection hashes, native
prediction bytes, frozen row/label order, exact comparator identity,
probability direction and unchanged point metrics. It fingerprints original
and normalized score vectors and records any CSV-roundtrip differences.
It then reproduces **both** original paired IID issue-bootstrap intervals
(2,000 draws, seed 7) and diagnostic non-circular moving-block intervals
(500 draws, seed 20261109, 20 chronological rows per block), using each
procedure's original score representation. A fixed bridge separately shows
the CSV representation, seed, draw-count and resampling-law changes; it is
not a search for a favorable interval. AP/ROC remain in JSON.

Replays that lack inputs or fail agreement are blocked individually. A
partial review quota or blocked reconciliation gives exit 2; a successful
export does **not** mean human review or history-based label validation is
complete. A second attempt requires a new `--batch-id`, preserving all
previous answers and the original source run.

### Verification commands and original local evidence

Local validation commands (no cluster submission):

```bash
cd /Users/yakovelmaleh/code/Master
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s Tasks/diagnose-instability-models/tests -v
bash -n Tasks/diagnose-instability-models/cluster/submit_jobs.sh
bash Tasks/run_cluster_task.sh diagnose-instability-models \
  --stage inventory --run-id launcher-check --partition main --dry-run
git diff --check
```

The tests cover identity-based alignment, corrupt/missing rows and scores,
frozen splits/labels, AUC-PRC versus AP, seals and prediction/metric drift,
deduplicated sampling probabilities, source-history validation, pending
reviews, review ingestion, offline pinned-tokenizer coverage, paired ranking
and uncertainty, external-only storage, dispatcher discovery, shell rendering,
the global concurrency guard, and mocked submission/job mapping.

See `HANDOFF.md` for the final executed run, actual validation count, supported
findings and the concise coordination-session handoff. **Do not check off
T1-T3 merely because these tools pass tests.** Source histories, missing neural
studies, human review and matched cross-family results remain prerequisites
for completing the investigation.
