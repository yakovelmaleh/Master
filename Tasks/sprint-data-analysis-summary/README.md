# Sprint summary: data analysis and model experiments

This folder keeps the sprint PowerPoint in the repository. Maintain this copy
when adding more experiments; a copy in Downloads is only for convenience.

## Presentation

`results/Master-Sprint-Summary-2026-09-24.pptx`

The deck uses the existing presentation template and contains 17 slides:

| Slides | Content |
|---|---|
| 1 | Sprint summary title |
| 2-5 | `unstable-user-story-timechart-live` |
| 6-9 | `unstable-user-story-timechart-without-pr-evidence` |
| 10-13 | `research-new-public-jira-repositories` |
| 14-17 | PR #357: `validate-refactored-model-per-dataset` |

Each task has an introduction, Data Analysis, results, and conclusions.
The first three tasks were measured on September 10, 2026; the presentation was
assembled on September 24, 2026. PR #357's model experiment was appended on
September 27, 2026, using cluster run `20260924-212251-041726`.
No Jira data was refreshed. The original 13 slides remain unchanged.

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
