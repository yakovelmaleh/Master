# MariaDB missing optional model features 2026-09-17

## Status

Closed - no pipeline failure.

## Scope

- Task: `jira-url-to-instability-model`
- Dataset: `MariaDB`
- Run ID: `20260917-204018`
- SLURM job: `21438426`
- Investigation PR: `#337`
- Investigation date: `2026-09-17`

## Symptom

The MariaDB SLURM output contained:

```text
RuntimeWarning: Mean of empty slice
```

This warning made the successful job appear to have failed.

## Root cause

All 169 accepted MariaDB rows had no value for
`original_story_points_sprint`. The model feature transformer calculated the
column median, which caused NumPy to warn because the entire column was empty.

The transformer then followed its intended fallback behavior:

- Missing median became `0.0`.
- All Story Points feature values became `0.0`.
- The feature was constant.
- Its trained coefficient was `0.0`.

`original_acceptance_criteria_sprint` was also empty for all accepted rows,
but it did not produce this numeric-median warning.

Confidence: high.

## Evidence

- The SLURM job downloaded all 360 selected issues with zero download errors.
- `cluster_run_summary.json` recorded one successful source and zero failures.
- Preprocessing accepted 169 rows and rejected 191:
  - 173 had no comment before sprint entry.
  - 18 had no reconstructable sprint entry.
- The model completed 391 training iterations.
- The 35-row chronological test partition produced:
  - F1: `0.5294`
  - ROC AUC: `0.6818`
  - Average precision: `0.4566`
- The MariaDB Jira field map exposed Story Points, but none of the accepted
  issues had a populated value.

## Impact

The pipeline, generated dataset, and trained model are valid. The issue caused
only a noisy warning and two unavailable optional features. It did not cause
job failure, data loss, or invalid numeric model parameters.

## Decision and actions

The user selected **stop without changes**. No model or pipeline fix was made,
and MariaDB was not rerun.

## Cleanup

- Copied investigation artifacts from PR `#337`: removed by this cleanup PR.
- Permanent diagnosis: retained in this README.
- Original cluster results under
  `Tasks/jira-url-to-instability-model/cluster_runs/20260917-204018/mariadb/`:
  not deleted by this PR because cluster runtime outputs are not tracked in
  Git and require separate explicit confirmation.

## Follow-up

Optional future improvement: update the feature transformer to detect
all-missing numeric columns without emitting a warning and record unavailable
features in model metadata.
