# 3. Preprocessing and issue validity

The preprocessing stage is implemented in
`jira_pipeline/preprocessing.py`.

## Text normalization

Jira Cloud may return description or custom text in Atlassian Document Format
instead of a plain string. The pipeline recursively converts this structure
to plain text.

## Sprint-entry time

The first sprint-entry timestamp is calculated from:

1. Sprint objects with a `startDate`.
2. Sprint changelog entries showing when the issue entered a sprint.

The earliest valid timestamp on or after issue creation is selected.

An issue is rejected when a sprint-entry timestamp cannot be calculated.
An empty current Sprint field alone does not reject an issue: historical
Sprint additions can still supply the entry time.

## Comment-before-sprint filter

All comment timestamps are compared with the calculated sprint-entry time.

The issue is accepted only when at least one comment was created at or before
sprint entry. This reproduces the important filter from
`delete_no_sprint_no_done.py`.

## First-hour handling

The legacy preprocessing ignores text and story-point changes made during the
first hour after issue creation. The refactored pipeline applies the same
one-hour rule.

## Reconstructing sprint-entry state

For summary, description, acceptance criteria, and story points:

1. Start with the current Jira value.
2. Find changes after sprint entry.
3. Use the first post-sprint change's `fromString` as the value that existed
   at sprint entry.
4. If there was no post-sprint change, keep the current value.

This produces:

- `original_summary_sprint`
- `original_description_sprint`
- `original_acceptance_criteria_sprint`
- `original_story_points_sprint`

## Rejection summary

Every issue produces either an accepted row or a rejection reason:

- `invalid_created`
- `no_sprint_entry`
- `no_comment_before_sprint`
- `accepted`

Counts are saved in:

```text
processed/filter_summary.json
```

The summary also records selected keys, download failures, the effective
query, and whether an issue limit was requested. Per-issue decisions are
saved to `processed/filter_decisions.csv`.

`processed/dataset_analysis.json` records positive and negative counts at
levels 5/10/15/20, together with the chronological train/validation/test
distributions and single-class warnings. These are label-distribution
diagnostics, not four trained-model results. They are written even when no
rows survive or the model cannot be trained.
