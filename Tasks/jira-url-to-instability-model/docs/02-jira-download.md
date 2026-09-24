# 2. Jira discovery and download

The download stage is implemented in `jira_pipeline/client.py`.

## Field discovery

The pipeline calls Jira's field endpoint and builds a name-to-ID map. This is
necessary because custom-field IDs differ between repositories.

The important fields are:

- `Sprint` — required.
- `Acceptance Criteria` — optional.
- `Story Points` — optional.

Standard fields such as summary, description, issue type, project, created
date, priority, creator, and reporter are also downloaded.

The discovered mapping is saved to:

```text
raw/field_map.json
```

## API detection

The client detects whether the Jira repository supports:

- Jira REST API v2 search; or
- the newer Jira Cloud v3 `/search/jql` endpoint.

This allows the same command to work with older Jira Server instances and
newer Atlassian Cloud instances.

## Issue selection

The client executes the effective JQL and paginates until all matching keys
are found, unless `--max-issues` was specified.

Selected keys are saved to:

```text
raw/issue_keys.json
```

Configured sources use the original status-or-resolution predicates; generic
URL runs use the portable Done-only policy. Current Sprint membership is not
required by default, because valid membership may exist only in the changelog.
GitHub-comment and pre-sprint-comment requirements are not removed.

## Detailed download

For each issue key, the pipeline downloads:

1. Current issue fields.
2. Every accessible comment page.
3. Every accessible changelog page.

Each complete issue record is written as one JSON line:

```text
raw/issues.jsonl
```

Issue-specific failures are recorded without hiding them:

```text
raw/download_errors.csv
```

## Reliability

Requests have:

- Explicit timeouts.
- Retries for rate limits and temporary server errors.
- Pagination for search, comments, and changelogs.
- Clear HTTP and invalid-JSON errors.

Without `--refresh`, cached issues are reused only when the saved URL,
project, effective query, and issue limit match. A changed or missing
configuration fails with instructions to refresh instead of silently
reusing a narrower dataset. Any issue-download failures fail the run after
writing the filtering and dataset-analysis artifacts.
