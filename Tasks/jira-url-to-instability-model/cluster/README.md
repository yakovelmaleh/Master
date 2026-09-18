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

Submit only selected sources:

```bash
./Tasks/run_cluster_task.sh \
  jira-url-to-instability-model \
  --only Qt \
  --refresh
```

This creates exactly one Qt SLURM job. Multiple names create one job per
selected source:

```bash
./Tasks/run_cluster_task.sh \
  jira-url-to-instability-model \
  --only MariaDB Qt \
  --refresh
```

Source names are validated before any job is submitted. Unknown or disabled
sources stop the command without creating partial submissions.

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
