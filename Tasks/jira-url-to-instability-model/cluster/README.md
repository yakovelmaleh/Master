# Cluster runner

This subfolder contains the batch entry point for running the new Jira URL to
instability model pipeline on the cluster.

It follows the existing Master cluster pattern: read Jira repositories from a
JSON source file and run the complete pipeline once for each repository.
Each source produces its own isolated folder under `runs/`.

## Default full cluster run

From `Tasks/jira-url-to-instability-model/`:

```bash
python3 -m pip install -r requirements.txt
python3 cluster/run_cluster.py --refresh
```

The default source file is:

```text
../../Source/jira_data_for_instability_cluster.json
```

That file currently selects Apache, Hyperledger, IntelDAOS, Jira, MariaDB,
and Qt. With no project configured, every repository is processed
cross-project.

## Safe bounded cluster test

```bash
python3 cluster/run_cluster.py \
  --only Apache Qt \
  --max-issues 100 \
  --refresh
```

## PR evidence

GitHub/PR evidence is enabled by default, matching the new pipeline:

```text
comment ~ "https://github.com"
```

Disable it for a separate experiment:

```bash
python3 cluster/run_cluster.py \
  --no-require-pr-evidence \
  --refresh
```

## Source file format

The existing source format works without changes:

```json
{
  "Apache": {
    "jira_url": "https://issues.apache.org/jira"
  }
}
```

Optional per-source settings are also supported:

```json
{
  "ApacheAria": {
    "jira_url": "https://issues.apache.org/jira",
    "project": "ARIA",
    "run_name": "apache-aria",
    "jql": "type != Bug"
  },
  "DisabledExample": {
    "jira_url": "https://example.atlassian.net",
    "enabled": false
  }
}
```

If `project` is omitted, the run is cross-project. The default run name is the
repository name, or `<repository>-<project>` when a project is configured.

## Behavior and outputs

- Repositories run sequentially to avoid overwhelming public Jira APIs.
- One repository failure does not stop the other repositories.
- `--fail-fast` stops on the first failure.
- Rerunning without `--refresh` reuses each repository's cached raw JSONL.
- `--output-root` can point to cluster-mounted persistent storage.
- `cluster_run_summary.json` records successes, failures, settings, and output
  locations.
- The process exits with code `1` if any repository failed, so the cluster job
  can detect a partial failure.

Each successful source still creates the standard pipeline output:

```text
runs/<repository>/
├── raw/
├── processed/
├── model/
└── run_config.json
```
