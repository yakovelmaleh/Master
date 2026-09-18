# Jira GitHub evidence filter leaves insufficient rows 2026-09-17

## Status

Fixed in PR `#343`; Jira rerun pending.

## Scope

- Task: `jira-url-to-instability-model`
- Dataset: `Jira`
- Run ID: `20260917-204018`
- SLURM job: `21438425`
- Investigation PR: `#343`
- Investigation date: `2026-09-17`

## Symptom

The Jira job downloaded three issues but stopped during model training:

```text
Failed Jira: At least 30 rows are required; received 1.
```

## Root cause

The shared cluster default requires a comment containing the exact text
`https://github.com`. Atlassian's public Jira currently has only three
completed, non-bug, sprint-assigned issues matching that strict filter. Two
were rejected because they had no comment at or before sprint entry, leaving
one valid model row.

The 30-row model minimum behaved correctly. The source-specific query was too
restrictive for Atlassian Jira.

Confidence: high.

## Evidence

- The strict run JQL returned exactly three keys:
  `BSERV-2826`, `JSWCLOUD-6615`, and `JSWSERVER-6615`.
- All three records downloaded with zero errors.
- Preprocessing accepted one record and rejected two with
  `no_comment_before_sprint`.
- The generated CSV contained only `BSERV-2826`.
- The same query without GitHub-comment evidence currently matches 2,847
  issues.
- The existing `Data/Jira/features_labels_table_os.csv` remains unchanged
  and contains 1,588 rows.

## Impact

Fresh Jira data reached preprocessing but could not produce a trainable model.
The existing Jira dataset and existing model-validation tasks were not
modified.

## Decision and actions

The user selected **disable GitHub-only evidence for the Jira source**.

- Cluster sources can now override `require_pr_evidence` per source.
- The Jira cluster source sets `require_pr_evidence` to `false`.
- Other Jira sources retain the shared default of `true`.
- Regression coverage verifies that the source override is loaded.

## Fix and validation

- Pull request: `#343`
- Task unit tests: passed.
- Live Jira query without GitHub-only evidence: HTTP `200`, 2,847 matches.
- Cluster rerun: pending after merge.

## Cleanup

- Copied investigation artifacts from PR `#343`: removed from the same PR.
- Permanent diagnosis: retained in this README.
- Original cluster results under
  `Tasks/jira-url-to-instability-model/cluster_runs/20260917-204018/jira/`:
  not deleted because they require separate explicit confirmation.

## Follow-up

After merging, pull and rerun only Jira:

```bash
./Master/Tasks/run_cluster_task.sh --pull-only

./Master/Tasks/run_cluster_task.sh \
  jira-url-to-instability-model \
  --only Jira \
  --refresh
```
