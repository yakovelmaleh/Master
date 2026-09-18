# Qt Jira search probe rejected as unbounded 2026-09-17

## Status

Fixed in PR `#341`; Qt rerun pending.

## Scope

- Task: `jira-url-to-instability-model`
- Dataset: `Qt`
- Run ID: `20260917-204018`
- SLURM job: `21438427`
- Investigation PR: `#341`
- Investigation date: `2026-09-17`

## Symptom

The Qt job stopped before issue download and final dataset creation with:

```text
Failed Qt: Neither Jira search endpoint is anonymously accessible.
```

## Root cause

Qt's Jira search API is anonymously accessible. The pipeline rejected it
because endpoint discovery sends the unbounded JQL probe:

```text
order by created asc
```

Qt's Jira Cloud instance rejects that probe with HTTP `400` and:

```text
Unbounded JQL queries are not allowed here. Please add a search restriction
to your query.
```

The client interprets every non-`200` probe response as an unavailable or
inaccessible endpoint and raises a misleading authentication error. The
actual bounded Qt JQL from `run_config.json` succeeds anonymously against
the same v3 endpoint.

Confidence: high.

## Evidence

- `/rest/api/3/field` returned HTTP `200`, allowing `field_map.json` to be
  created.
- Legacy `/rest/api/2/search` returned HTTP `410` because that API has been
  removed.
- `/rest/api/3/search/jql` returned HTTP `400` for the client's unbounded
  endpoint probe.
- The same v3 endpoint returned HTTP `200` for the job's actual bounded JQL
  and returned issue key `QTBUG-16556`.
- `jira_pipeline/client.py:93-112` requires HTTP `200` from the unbounded
  probe before selecting the v3 endpoint.
- No `issue_keys.json`, `issues.jsonl`, processed CSV, or model artifacts
  were produced because execution stopped during endpoint discovery.

## Impact

The Qt source cannot proceed past Jira endpoint discovery, so no issues are
downloaded and no dataset or model is created. This is a client compatibility
bug, not a Qt authentication or permission problem.

## Decision and actions

The user selected **fix in the same investigation PR**.

- Endpoint discovery now probes with the actual bounded run JQL.
- The probe requests only the issue key and one result.
- Failure messages now retain the v2 and v3 HTTP status and response details.
- Regression tests cover Jira Cloud's removed v2 endpoint, successful v3
  fallback, use of the bounded query, and endpoint-specific errors.

## Fix and validation

- Pull request: `#341`
- Unit tests: passed.
- Live Qt bounded search smoke test: returned issue key `QTBUG-16556`.
- Qt cluster rerun: pending after merge.

## Cleanup

- Copied investigation artifacts from PR `#341`: removed from the same PR
  after diagnosis.
- Permanent diagnosis: retained in this README.
- Original cluster results under
  `Tasks/jira-url-to-instability-model/cluster_runs/20260917-204018/qt/`:
  not deleted because cluster runtime outputs are not tracked in Git and
  require separate explicit confirmation.

## Follow-up

After merging, pull the changes and rerun only Qt:

```bash
./Master/Tasks/run_cluster_task.sh --pull-only

./Master/Tasks/run_cluster_task.sh \
  jira-url-to-instability-model \
  --only Qt \
  --refresh
```
