# Sprint summary: data analysis and model experiments

This folder keeps the sprint PowerPoint in the repository. Maintain this copy
when adding more experiments; a copy in Downloads is only for convenience.

## Presentation

`results/Master-Sprint-Summary-2026-09-24.pptx`

The deck uses the existing presentation template and contains 29 slides:

| Slides | Content |
|---|---|
| 1 | Sprint summary title |
| 2-5 | `unstable-user-story-timechart-live` |
| 6-9 | `unstable-user-story-timechart-without-pr-evidence` |
| 10-13 | `research-new-public-jira-repositories` |
| 14-17 | PR #357: `validate-refactored-model-per-dataset` |
| 18-21 | PR #360: `compare-models-leave-one-project-out` |
| 22-25 | PR #358: `verify-refactored-instability-model` |
| 26-29 | PR #365: `evaluate-logistic-instability-model` |

Each task has an introduction, Data Analysis, results, and conclusions.
Each model task's introduction is its own two-column **Item / This task**
table, not a side-by-side comparison with another task.
The first three tasks were measured on September 10, 2026; the presentation was
assembled on September 24, 2026. PR #357's model experiment was appended on
September 27, 2026, using cluster run `20260924-212251-041726`.
PR #360 was also appended on September 27, 2026, using cluster run
`20260924-212328-564730`. No Jira data was refreshed. The existing slides,
including #357's section, remain unchanged when appending #360.
PR #358 was appended on September 27, 2026, using cluster run
`20260924-212306-286254`, preserving all 21 preceding slides.
PR #365 was appended on September 27, 2026. The model-task introduction slides
were subsequently replaced with individual overview tables; their data,
results, and conclusion slides remain unchanged. The standalone comparison
slide was removed.

## PR #357 experiment

The four added slides cover the introduction, baseline-versus-refactored Data
Analysis, results, and conclusions. They compare RF, legacy boosting, and NN at
unstable levels 5/10/15/20 across six repositories, with 144 reported outputs.
Both variants use the same historical CSV rows, chronological within-project
splits, and refactored pre-sprint features. Only training balancing differs.

The results table reports equal-weight six-project means of trapezoidal AUC-PRC,
not average precision or pooled-prediction scores. Refactored variants improve
32 of 72 paired comparisons; the overall descriptive mean falls from 0.2175
to 0.2049. This is not a statistical-significance claim. The baseline is not an
exact replay of the original rich-feature pipeline, and legacy "XGboost" denotes
`GradientBoostingClassifier`, not `XGBClassifier`.

Evidence: PR #357, artifact commit
`028b4e40f81ce29f00ae561f795a6df8a52adb7b`, bundle
`Tasks/task-summaries/validate-refactored-model-per-dataset-20260927-134055/`.
`RESULTS.csv` supplies the reported metrics; each project's
`artifacts/cluster-run/<project>/results/model/split_manifest.json` supplies
partition counts and evaluation policies. Scores were aggregated from the
reported metrics, not independently recomputed from predictions. Provenance
and detailed counts are also included in the new slides' speaker notes.

## PR #360 experiment

**Research question (slide 18):** Can a model trained on five repositories
predict instability in a sixth repository it has never seen?

The four added slides cover introduction, baseline-versus-refactored Data
Analysis, results, and conclusions for leave-one-project-out evaluation.
For each fold, the entire held-out repository is the test set; the other five
repositories are combined and split chronologically into approximately 80%
training and 20% validation. The held-out project is absent from both.
The same 23,822 eligible historical CSV rows are used across six folds,
four unstable levels, three model families, and two variants: all 144 outputs
are present and all six verification manifests report success.

Training-only balancing wins 20 of 72 paired comparisons and loses 52. The
descriptive macro AUC-PRC decreases from 0.1861 to 0.1753; only legacy boosting
at level 20 improves in the six-project model/level averages. The highest
individual result is Jira, baseline legacy boosting, level 5: 0.5059 AUC-PRC
with 34.6% test prevalence.

This tests project transfer, not strictly future-time transfer: source and
target dates overlap. Test populations differ from #357, so differences between
the two experiments are not paired improvement estimates. Macro scores are not
pooled-prediction scores or statistical-significance evidence. The same
historical-pipeline and legacy-model naming caveats described above apply.

Evidence: PR #360, artifact commit
`e554ad3e3fecfb9e5c0e3e40665274ff9bcb3f6a`, bundle
`Tasks/task-summaries/compare-models-leave-one-project-out-20260927-135429/`.
Aggregates use `RESULTS.csv`; fold counts and isolation use each project's
`artifacts/cluster-run/<project>/results/model/split_manifest.json`.
Success is recorded in `results/verification_manifest.json`. Individual
predictions were not independently rescored. Detailed provenance, counts,
date ranges, and metrics are included in the new slides' speaker notes.

## PR #358 experiment

**Research question (slide 22):** Can a model trained on older data from multiple
repositories predict instability in newer issues?

The four added slides cover introduction, baseline-versus-refactored Data
Analysis, results, and conclusions for pooled chronological evaluation. All
23,822 eligible rows are globally time-sorted, then split into 14,293 training,
4,764 validation, and 4,765 test rows. One grouped job completed all 24 outputs:
four unstable levels, three model families, and two variants.

Training-only balancing improves AUC-PRC in 5 of 12 matched comparisons and
reduces it in 7. The descriptive mean across 12 model/level scores is almost
unchanged: 0.09807 baseline versus 0.09801 refactored. This is not a statistical
equivalence claim. The best individual AUC-PRC is baseline legacy boosting at
level 5: 0.1470, with ROC AUC 0.6138.

The global test window spans September 29, 2021 through April 27, 2023.
It contains Qt (2,669 rows), Apache (1,841), MariaDB (239), and Jira (16);
Hyperledger and IntelDAOS have no test rows. Qt and Apache account for 94.6%
of test rows. Positive counts at levels 5/10/15/20 are 504/325/240/191.
These are pooled test scores, not six-project macro means, and are not directly
matched to #357 or #360's different test populations. The historical-pipeline
and legacy-model naming caveats above still apply.

Evidence: PR #358, artifact commit
`613d77153bb4f3f00c8111290caa2a767302309e`, bundle
`Tasks/task-summaries/verify-refactored-instability-model-20260927-134800/`.
Metrics come from `RESULTS.csv`, with provenance and split details under
`artifacts/cluster-run/all/results/`. All 24 run metadata files were checked
for identical test-row hashes, unweighted test evaluation, validation-based
selection, and the refactored training-balancing policy. Scores were not
independently recomputed from predictions. Detailed metrics and source
provenance are included in the new slides' speaker notes.

## PR #365 experiment

**Research question (slide 26):** How well does a simple logistic model predict
newer issues from older multi-repository data, using the pooled split?

Cluster run `20260924-212357-961761` completed four logistic outputs at levels
5/10/15/20. It uses 23,822 eligible rows and the same 14,293/4,764/4,765 split
counts as #358. At every level, validation/test issue-key and label sequences
match #358, and saved feature transformers are identical.

This is a separate dependency-light logistic model, not another matched
baseline/refactored pair. Training is class-weighted; saved-iterate selection
uses **balanced validation log loss**, unlike #358's validation AUC-PRC
selection. Threshold selection uses validation F1. Reported metrics are
unweighted. The change is therefore not an estimator-only comparison.

| Level | Test AUC-PRC | Average precision | Accuracy | ROC AUC |
|---|---:|---:|---:|---:|
| 5 | 0.1454 | 0.1463 | 56.03% | 0.5933 |
| 10 | 0.1157 | 0.1171 | 84.51% | 0.6493 |
| 15 | 0.1027 | 0.1044 | 86.27% | 0.6912 |
| 20 | 0.0820 | 0.0841 | 88.92% | 0.6779 |

At level 5, precision is 13.12% and recall is 56.15%. Always predicting stable
would yield 89.42% accuracy but zero unstable recall. No unweighted logistic
control is included, so this experiment cannot isolate balancing's effect.
The pooled test population has the same coverage limitations as #358.

Evidence: PR #365, artifact commit
`05384024a0abf96b2b60f786f4e5a63ba584aa7e`, bundle
`Tasks/task-summaries/evaluate-logistic-instability-model-20260927-144611/`.
Reported results and per-level metrics/metadata come from
`artifacts/cluster-run/all/results/model/words_<level>/Logistic/logistic/all_words_<level>/`.
The bundled `unstable_model/model.py` documents weighting and saved-iterate
selection. Metrics were not independently rescored from predictions.

## Individual task overview tables

Slides 14 (#357), 18 (#360), 22 (#358), and 26 (#365) each explain only their
own task in a two-column **Item / This task** table. Every table includes:
research question, training data, split, models trained, test coverage,
results/aggregation, and completed outputs. There is no standalone
task-versus-task comparison slide.

## Open and update

Open the `.pptx` in PowerPoint. On macOS, from the repository root:

```bash
open Tasks/sprint-data-analysis-summary/results/Master-Sprint-Summary-2026-09-24.pptx
```

Append future experiment sections to this deck and submit the updated file
through a pull request. This change versions the finished presentation and its
guide; local authoring tools and the unfinished presentation skill are separate.

## Data interpretation

Candidate counts are not unstable labels or final model-ready rows. Neither
time-chart cohort has passed the comment-before-sprint filter. All strict-cohort
issue keys are present in the wider cohort; duplicate keys and daily aggregate
totals were checked before generation. Public-Jira research counts are API
estimates, and compatibility checks cover only one sample issue per source.
The September 24 cluster selection changes are not retroactively applied to
these September 10 experiments.

Source filenames, cohort definitions, and measurement dates are included in
slide notes. No AUC-PRC or other model scores are invented for these data tasks.
