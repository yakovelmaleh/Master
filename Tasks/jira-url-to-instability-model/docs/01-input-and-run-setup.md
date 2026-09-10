# 1. Input and run setup

The pipeline starts from a Jira repository URL:

```bash
python3 run_pipeline.py \
  --jira-url https://issues.apache.org/jira
```

If `--project` is omitted, all matching projects in the Jira repository are
processed together as a cross-project dataset:

```bash
python3 run_pipeline.py \
  --jira-url https://issues.apache.org/jira
```

To process only one project:

```bash
python3 run_pipeline.py \
  --jira-url https://issues.apache.org/jira \
  --project ARIA
```

## Run naming

The default output name is derived from the URL:

- Apache cross-project: `runs/apache/`
- Apache ARIA: `runs/apache-aria/`
- MongoDB cross-project: `runs/mongodb/`

Use `--run-name` to override it.

## Default selection

The default Jira query requires:

1. An issue type other than `Bug`.
2. A non-empty Sprint field.
3. `statusCategory = Done`.
4. A Jira comment containing `https://github.com`.

The effective query is stored in `run_config.json`.

Disable optional restrictions with:

```bash
--no-terminal-only
--no-require-pr-evidence
```

Replace the default `type != Bug` condition with:

```bash
--jql 'issuetype in (Story, Task)'
```

## Authentication

Public Jira repositories normally require no credentials.

For Jira Cloud:

```bash
export JIRA_EMAIL="user@example.com"
export JIRA_TOKEN="api-token"
```

For bearer-token authentication, set only `JIRA_TOKEN`.

## Safe testing

Limit the number of downloaded issues while testing:

```bash
python3 run_pipeline.py \
  --jira-url https://issues.apache.org/jira \
  --project ARIA \
  --max-issues 100 \
  --run-name apache-aria-sample
```
