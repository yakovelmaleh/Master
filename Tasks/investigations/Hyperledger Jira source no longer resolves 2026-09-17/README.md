# Hyperledger Jira source no longer resolves 2026-09-17

## Status

Mitigated in PR `#344`; fresh Hyperledger Jira ingestion disabled.

## Scope

- Task: `jira-url-to-instability-model`
- Dataset: `Hyperledger`
- Run ID: `20260917-204018`
- SLURM job: `21438423`
- Investigation PR: `#344`
- Investigation date: `2026-09-17`

## Symptom

The job could not connect to the configured Jira hostname:

```text
Failed to establish a new connection:
[Errno -2] Name or service not known
```

## Root cause

The configured hostname `jira.hyperledger.org` no longer resolves in DNS.
The Linux Foundation Hyperledger project guidance now directs projects to
track issues in their project systems, commonly GitHub Issues. No compatible
replacement Jira REST endpoint was found for the Jira-only pipeline.

Confidence: high for the unavailable configured source; medium for permanent
retirement because no formal shutdown notice was found.

## Evidence

- The cluster failed during the first field-discovery request.
- DNS lookup for `jira.hyperledger.org` failed.
- `lf-hyperledger.atlassian.net` resolves, but its Jira REST field endpoints
  return HTTP `404` and are not a replacement issue API.
- Current Hyperledger project best practices direct contributors to GitHub
  issue trackers.
- The existing `Data/Hyperledger/features_labels_table_os.csv` remains
  available with 4,819 rows.

## Impact

Fresh Hyperledger data cannot be produced by the Jira URL pipeline. Existing
CSV-based model validation remains available and unchanged.

## Decision and actions

The user selected **disable the stale Hyperledger Jira source while retaining
the existing CSV dataset**.

- The Hyperledger entry is disabled only in
  `Source/jira_data_for_instability_cluster.json`.
- The source URL remains recorded for provenance.
- The existing `Data/Hyperledger/` dataset is not modified.

## Fix and validation

- Pull request: `#344`
- Cluster source loading already has coverage for disabled entries.
- Fresh Hyperledger rerun: not applicable until a new ingestion source is
  selected.

## Cleanup

- Copied investigation artifacts from PR `#344`: removed from the same PR.
- Permanent diagnosis: retained in this README.
- Original cluster results under
  `Tasks/jira-url-to-instability-model/cluster_runs/20260917-204018/hyperledger/`:
  not deleted because they require separate explicit confirmation.

## Follow-up

If fresh Hyperledger data is required, create a separate GitHub Issues
ingestion task instead of treating GitHub as a Jira-compatible endpoint.
