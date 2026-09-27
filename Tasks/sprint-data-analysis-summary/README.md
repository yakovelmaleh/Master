# Sprint summary: data analysis and model experiments

This folder keeps the sprint PowerPoint in the repository. Maintain this copy
when adding more experiments; a copy in Downloads is only for convenience.

## Presentation

`results/Master-Sprint-Summary-2026-09-24.pptx`

The deck uses the existing presentation template and contains 21 slides:

| Slides | Content |
|---|---|
| 1 | Sprint summary title |
| 2-5 | `unstable-user-story-timechart-live` |
| 6-9 | `unstable-user-story-timechart-without-pr-evidence` |
| 10-13 | `research-new-public-jira-repositories` |
| 14-17 | PR #357: `validate-refactored-model-per-dataset` |
| 18-21 | PR #360: `compare-models-leave-one-project-out` |

Each task has an introduction, Data Analysis, results, and conclusions.
The first three tasks were measured on September 10, 2026; the presentation was
assembled on September 24, 2026. PR #357's model experiment was appended on
September 27, 2026, using cluster run `20260924-212251-041726`.
PR #360 was also appended on September 27, 2026, using cluster run
`20260924-212328-564730`. No Jira data was refreshed. The existing slides,
including #357's section, remain unchanged when appending #360.

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
