# Jira URL to instability data and model

This task is the complete reusable pipeline requested for new Jira
repositories and refreshed data from existing repositories.

**Input:** a Jira repository URL, with an optional project key and JQL filter.

**Output:** raw downloaded issues, comments and changelogs; a fully
preprocessed instability dataset; and a trained model with metrics,
predictions, coefficients, and a readable HTML report.

## Detailed five-part explanation

The complete process is explained in these five ordered files:

1. [`docs/01-input-and-run-setup.md`](docs/01-input-and-run-setup.md)
2. [`docs/02-jira-download.md`](docs/02-jira-download.md)
3. [`docs/03-preprocessing-and-validity.md`](docs/03-preprocessing-and-validity.md)
4. [`docs/04-dataset-features-and-labels.md`](docs/04-dataset-features-and-labels.md)
5. [`docs/05-training-outputs-and-reruns.md`](docs/05-training-outputs-and-reruns.md)

## What is inside

- `run_pipeline.py` - the single end-to-end command.
- `cluster/submit_jobs.sh` - production SLURM launcher that submits one
  independent job per Jira repository with isolated results and `.out` logs.
- `cluster/run_cluster.py` - batch cluster entry point that reads the existing
  Jira source JSON and executes the new pipeline for every repository.
- `cluster/README.md` - cluster setup, commands, configuration, and outputs.
- `jira_pipeline/client.py` - Jira REST discovery, authentication, pagination,
  retries, issue download, comments, and changelog download.
- `jira_pipeline/preprocessing.py` - sprint-entry reconstruction, comment
  validity filtering, sprint-entry text reconstruction, instability labels,
  and pre-sprint model features.
- `jira_pipeline/orchestrator.py` - persistent run folders and stage wiring.
- `jira_pipeline/cli.py` - command-line interface.
- `unstable_model/` - self-contained deterministic model trainer copied into
  this task so it does not depend on another task folder.
- `model_config.json` - model and chronological split configuration.
- `requirements.txt` - runtime dependencies.
- `runs/` - one isolated output folder per execution.

## Preprocessing reproduced

1. Select non-bug issues by default.
2. For configured cluster sources, use the original source-specific status
   **or** resolution condition. A standalone URL uses `statusCategory = Done`.
3. Keep the existing GitHub-comment evidence requirement (Apache also accepts
   the original PR labels; the existing Jira source exception remains).
4. Require reconstructable sprint history, not a populated current Sprint field.
5. Download all issue comments and changelog pages.
6. Calculate first sprint entry from sprint start metadata and Sprint
   changelog history.
7. Reject issues without a valid sprint-entry timestamp.
8. Reject issues without a comment at or before sprint entry.
9. Ignore text changes made during the first hour after issue creation.
10. Reconstruct summary, description, acceptance criteria, and story points at
   sprint entry.
11. Count post-sprint text changes and changed words.
12. Create the 5/10/15/20-word instability labels.
13. Calculate only pre-sprint model features.
14. Train with a chronological 60/20/20 split.

The implementation intentionally replaces broad exception handling and
hard-coded paths from the original scripts with explicit errors, field
discovery, retry logic, cached raw data, and deterministic artifacts.

## Authentication

Public Jira repositories need no credentials.

For Jira Cloud basic authentication:

```bash
export JIRA_EMAIL="user@example.com"
read -r -s -p "Jira token: " JIRA_TOKEN
echo
export JIRA_TOKEN
```

For a bearer token, set only `JIRA_TOKEN`.

## Run a new repository

When `--project` is omitted, the pipeline performs a cross-project run over
all matching projects in that Jira repository:

```bash
python3 run_pipeline.py \
  --jira-url https://issues.apache.org/jira
```

The default run folder is derived from the repository name:

- Apache without a project: `runs/apache/`
- Apache with `--project ARIA`: `runs/apache-aria/`
- MongoDB without a project: `runs/mongodb/`

You can still override the folder with `--run-name`.

To run one project:

```bash
python3 run_pipeline.py \
  --jira-url https://example.atlassian.net \
  --project EXAMPLE \
  --run-name example
```

## Refresh an existing repository

```bash
python3 run_pipeline.py \
  --jira-url https://issues.apache.org/jira \
  --project ARIA \
  --run-name apache-aria \
  --refresh
```

## Run all configured repositories on the cluster

```bash
./Tasks/run_cluster_task.sh --pull jira-url-to-instability-model --refresh
```

Run this command from the repository root. It optionally updates the checkout,
then submits one SLURM job per repository. Results and `.out` logs are grouped
under a timestamped `cluster_runs/<run-id>/<repository>/` directory, with a
`submitted_jobs.tsv` index. See [`cluster/README.md`](cluster/README.md) for
the exact layout, bounded tests, source overrides, and sequential local runs.

Omit `-jira` to submit all enabled repositories, one dedicated job per
repository. To submit only Qt:

```bash
./Tasks/run_cluster_task.sh jira-url-to-instability-model -jira Qt --refresh
```

`--only` remains a compatible alias for `-jira`. Disabled source entries are
not submitted.

## Safe bounded test

```bash
python3 run_pipeline.py \
  --jira-url https://issues.apache.org/jira \
  --project ARIA \
  --run-name apache-aria-sample \
  --max-issues 100 \
  --refresh
```

## Validated bounded E2E run

On September 10, 2026, the complete pipeline was run against 100 Apache
cross-project issues with the default GitHub/PR-evidence filter enabled.

- 100 issues downloaded with no download errors.
- 68 issues passed preprocessing.
- 29 were rejected for having no comment at or before sprint entry.
- 3 were rejected because sprint entry could not be reconstructed.
- The processed dataset and every model artifact were created successfully.

The run and its own README are stored in:

```text
runs/apache-e2e-sample/
```

This sample verifies the E2E mechanics. It is intentionally too small for
model-quality conclusions.

## Filter controls

- Status/resolution filtering and GitHub/PR evidence are enabled by default.
- `--no-terminal-only` removes the status/resolution condition.
- `--no-require-pr-evidence` removes the GitHub/PR condition.
- `--jql 'issuetype in (Story, Task)'` replaces the default `type != Bug`
  issue condition while retaining project and sprint requirements.
- `--label-threshold 10` trains with the ten-word instability label.
- `--require-current-sprint` restores the narrower current-Sprint JQL filter
  for an explicitly separate experiment.

The cluster source file stores `terminal_jql` conditions copied from
`Data_Analysis/JQL_Queries.py`; regression tests check their equivalence.
These historical conditions include some active statuses and must not be
described as Done-only. Unknown sources and standalone URL runs retain the
portable `statusCategory = Done` default. Use `--jql` with
`--no-terminal-only` for a standalone source-specific query.

The pre-sprint-comment filter is unchanged: it was already part of the
original pipeline. Restoring issue selection does not guarantee the same
historical row count because the live repository and accessible history change.

## Run output

Each `runs/<run-name>/` folder contains:

- `run_config.json` - exact URL, project, JQL, API, and options.
- `raw/field_map.json` - discovered Jira fields.
- `raw/issue_keys.json` - selected issue keys.
- `raw/issues.jsonl` - downloaded issue fields, comments, and changelogs.
- `raw/download_errors.csv` - issue-specific download failures.
- `processed/filter_summary.json` - accepted and rejected counts.
- `processed/filter_decisions.csv` - each downloaded issue and its acceptance
  or rejection reason.
- `processed/dataset_analysis.json` - label counts and chronological partition
  distributions for all four levels, including single-class warnings.
- `processed/<project>/features_labels_table_os.csv` - model dataset.
- `model/<project>_words_<threshold>/` - model, transformer, predictions,
  metrics, coefficients, metadata, and `report.html`.

Rerunning without `--refresh` reuses raw JSONL only if the URL, project,
effective query, and issue limit match the saved configuration. Changed
selection settings require `--refresh` or a new run folder, preventing an old
86-issue cache from masquerading as a broader collection. Download failures
are recorded and fail the run instead of training silently on incomplete data.

Dataset diagnostics are written before training. Training fails explicitly
when its training or validation partition has only one class; the dataset and
diagnostics remain available for inspection.

## Tests

The tests use synthetic Jira issue, comment, changelog, and model data. They
do not call a live Jira repository:

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -v
```

## Important compatibility note

Jira repositories use different custom-field names and permissions. The
pipeline discovers fields named `Sprint`, `Acceptance Criteria`, and
`Story Points`. Sprint is required; acceptance criteria and story points are
optional. Private comments or changelogs require credentials with permission
to read them.
