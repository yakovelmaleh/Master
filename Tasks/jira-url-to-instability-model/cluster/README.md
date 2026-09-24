# Cluster runner

This task owns two cluster entry points:

- `submit_jobs.sh` submits one independent SLURM job per Jira source.
- `run_cluster.py` runs selected sources sequentially inside the current
  process. The SLURM launcher calls it once per source.

Use `submit_jobs.sh` for production cluster runs. Every submission gets a
timestamped directory, and every Jira has separate results, logs, and its
generated sbatch file.

## Recommended cluster command

From the repository root:

```bash
./Tasks/run_cluster_task.sh --pull jira-url-to-instability-model --refresh
```

`--pull` runs `git pull --ff-only` before jobs are submitted. Omit it when the
cluster checkout is already current or when you intentionally want to run the
checked-out version:

```bash
./Tasks/run_cluster_task.sh jira-url-to-instability-model --refresh
```

From this task folder, the equivalent direct command is:

```bash
./cluster/submit_jobs.sh --refresh
```

Without `-jira` (or the compatible `--only` alias), all enabled repositories
are submitted, each in its own SLURM job with separate results and logs.
Entries marked `enabled: false` remain skipped.

Submit only Qt:

```bash
./Tasks/run_cluster_task.sh \
  jira-url-to-instability-model \
  -jira Qt \
  --refresh
```

This creates exactly one Qt SLURM job. Multiple names create one job per
selected source:

```bash
./Tasks/run_cluster_task.sh \
  jira-url-to-instability-model \
  -jira MariaDB Qt \
  --refresh
```

Source names are validated before any job is submitted. Unknown or disabled
sources stop the command without creating partial submissions.
`-jira` and `--only` are also handled after a `--` separator; they cannot be passed through
to override every generated job with Qt. The launcher owns `--output-root`
and rejects attempts to override it. Reusing a run ID fails without altering
the existing results. The selected source configuration is copied to
`cluster_runs/<run-id>/sources.json` before submission.

The launcher uses the existing cluster settings:

- Partition: `main`
- Time: `4-03:30:00`
- Tasks: `2`
- CPUs per task: `6`
- Memory: `16G`
- Conda environment: `master`
- Mail: `yakovelm@post.bgu.ac.il`, all job events

Override the partition, time, or environment when needed:

```bash
./cluster/submit_jobs.sh \
  --partition debug \
  --time 02:00:00 \
  --conda-env master \
  --max-issues 100 \
  --refresh
```

## Output and log ownership

A run started at `20260917-195500` is organized as:

```text
cluster_runs/20260917-195500/
├── submitted_jobs.tsv
├── apache/
│   ├── submit.sbatch
│   ├── logs/
│   │   └── job-<SLURM_JOB_ID>.out
│   └── results/
│       ├── cluster_run_summary.json
│       └── apache/
│           ├── raw/
│           ├── processed/
│           ├── model/
│           └── run_config.json
└── qt/
    └── ...
```

`submitted_jobs.tsv` is the index for the whole submission. It records each
source name, SLURM job ID, results directory, `.out` log pattern, and generated
sbatch path. `cluster_runs/latest_run.txt` contains the newest run directory.

The generated `cluster_runs/` content is ignored by Git.

## Preview without submitting

Use dry-run mode to validate paths and generated sbatch files without calling
SLURM:

```bash
./cluster/submit_jobs.sh --dry-run --max-issues 100 --refresh
```

## Source file

The default source file is:

```text
../../Source/jira_data_for_instability_cluster.json
```

Use another source file when needed:

```bash
./cluster/submit_jobs.sh \
  --sources-file /path/to/recommended_sources.json \
  --refresh
```

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

## Safe bounded cluster test

```bash
./cluster/submit_jobs.sh --max-issues 100 --refresh
```

## PR evidence

GitHub/PR evidence is enabled by default:

```text
comment ~ "https://github.com"
```

Disable it for a separate experiment:

```bash
./cluster/submit_jobs.sh --no-require-pr-evidence --refresh
```

The source file's `terminal_jql` predicates preserve the original per-source
status **or** resolution lists from `Data_Analysis/JQL_Queries.py`, rather than
replacing them with Done-only. Apache's `pr_evidence_jql` also accepts its
original PR labels. Jira retains its existing `require_pr_evidence: false`
exception. Explicit CLI switches take precedence over source defaults.
Unknown sources without these predicates use the portable defaults.

Current Sprint membership is no longer a query requirement. Preprocessing
still requires a recoverable sprint entry and at least one pre-sprint comment,
as before. `--require-current-sprint` requests the old narrow query explicitly.

After collection, inspect `processed/filter_summary.json`,
`processed/filter_decisions.csv`, and `processed/dataset_analysis.json`
inside each source's results. They show collection losses and label/split
counts for all levels before training. A single-class training or validation
partition fails the job rather than producing a misleading successful model.

## Sequential local run

For a local run without SLURM:

```bash
python3 cluster/run_cluster.py --refresh
```

For a bounded sequential test:

```bash
python3 cluster/run_cluster.py \
  --only Apache Qt \
  --max-issues 100 \
  --refresh
```

The sequential runner writes to `runs/` by default. One repository failure
does not stop the other repositories unless `--fail-fast` is supplied.
It also accepts `-jira` as an alias for `--only`, but only the shell launcher
creates separate SLURM jobs.
