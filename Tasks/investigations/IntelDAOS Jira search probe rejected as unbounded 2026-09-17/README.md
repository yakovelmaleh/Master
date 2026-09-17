# IntelDAOS Jira search probe rejected as unbounded 2026-09-17

## Status

Fixed by PR `#341`; IntelDAOS rerun pending.

## Scope

- Task: `jira-url-to-instability-model`
- Dataset: `IntelDAOS`
- Run ID: `20260917-204018`
- SLURM job: `21438424`
- Investigation PR: `#342`
- Investigation date: `2026-09-17`

## Symptom

The job stopped before issue download and final dataset creation with:

```text
Failed IntelDAOS: Neither Jira search endpoint is anonymously accessible.
```

## Root cause

This is the same endpoint-discovery bug diagnosed for Qt in PR `#341`.
IntelDAOS uses Jira Cloud. Its legacy v2 search endpoint is removed, and its
v3 endpoint rejects the client's unbounded probe:

```text
order by created asc
```

The client interpreted the non-`200` probe as an authentication failure.
The actual bounded IntelDAOS run JQL succeeds anonymously against the v3
endpoint and returns issue `DAOS-2`.

Confidence: high.

## Evidence

- Field discovery succeeded and produced `field_map.json`.
- The cluster summary recorded zero successes and one endpoint-discovery
  failure.
- A live request using the actual bounded run JQL returned HTTP `200`.
- No issue keys, downloaded records, processed dataset, or model artifacts
  were produced.
- PR `#341` changes endpoint discovery to probe with the actual bounded JQL
  and preserves endpoint-specific HTTP diagnostics.

## Impact

Fresh IntelDAOS data could not be downloaded in this run. The existing
`Data/IntelDAOS/features_labels_table_os.csv` dataset remains unchanged and
contains 1,666 rows.

## Decision and actions

The user selected **reuse the shared fix from PR #341**. The endpoint fix is
not duplicated in this PR.

## Fix and validation

- Fix pull request: `#341`
- IntelDAOS live bounded search: HTTP `200`, issue `DAOS-2`
- Cluster rerun: pending after PR `#341` merges

## Cleanup

- Copied investigation artifacts from PR `#342`: removed from the same PR.
- Permanent diagnosis: retained in this README.
- Original cluster results under
  `Tasks/jira-url-to-instability-model/cluster_runs/20260917-204018/inteldaos/`:
  not deleted because they require separate explicit confirmation.

## Follow-up

After merging PR `#341`, pull and rerun only IntelDAOS:

```bash
./Master/Tasks/run_cluster_task.sh --pull-only

./Master/Tasks/run_cluster_task.sh \
  jira-url-to-instability-model \
  --only IntelDAOS \
  --refresh
```
