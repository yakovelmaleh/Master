# Prepare code-smell dataset

First of three tasks: prepare stories and pinned code evidence, then run
`detect-code-smells`, then `train-code-smell-models`. The shared implementation is
in `Code_Smells_Detection/runtime/`; the old detector entry points are not used.

## Study contract

Use the saved September 10 candidate CSV and adjacent `source_status.csv`.
The candidate SHA256 is
`a96d260478dfe2c6eb78ce8c47bac74707039c05853e90e0c8e2775d103d0aab`.
Its 68,358 IDs are preliminary candidates, not labeled or split model rows.
The four sources with at least 100 candidates are Apache, IntelDAOS, MongoDB
and RedHat (68,244 candidates total). No new JQL population is collected.

Enrichment reconstructs sprint-entry text and metadata, applying the existing
story/comment validity rules. Splits are frozen **before** code or detector
exclusions. Verified matching prior features and membership are reused;
otherwise the task freezes chronological 60/20/20 train/validation/test
partitions per source, with source-qualified row IDs breaking timestamp ties.
Later stages only mask these partitions; they never re-split surviving rows.

## Submit stages

Run from the repository root on the cluster. Paths must be visible to workers.
Keep storage outside Git and separate from active HF environments and runs.
Copy the two original CSVs to `$INPUTS`; do not regenerate them.

```bash
STORAGE="$HOME/master-code-smells"
RUN="code-smells-001"
INPUTS="$HOME/code-smell-inputs"

# Bootstrap from an existing environment with Python and conda.
# Creates master-smells; does not install into master or HF environments.
bash Tasks/run_cluster_task.sh prepare-code-smell-dataset \
  --stage environment --storage "$STORAGE" --run-id "$RUN" --conda-env master

# Wait for each stage to succeed before submitting the next one.
bash Tasks/run_cluster_task.sh prepare-code-smell-dataset \
  --stage audit --storage "$STORAGE" --run-id "$RUN" \
  --candidates "$INPUTS/live_model_candidates.csv" \
  --sources "$INPUTS/source_status.csv"

bash Tasks/run_cluster_task.sh prepare-code-smell-dataset \
  --stage enrich --storage "$STORAGE" --run-id "$RUN"
bash Tasks/run_cluster_task.sh prepare-code-smell-dataset \
  --stage freeze --storage "$STORAGE" --run-id "$RUN"
bash Tasks/run_cluster_task.sh prepare-code-smell-dataset \
  --stage fetch-code --storage "$STORAGE" --run-id "$RUN"
```

Add `--dry-run` to print the sbatch script without submission. Source stages
default to all retained sources; `--source Apache` selects one. Arrays run at
most two workers concurrently, and another code-smell array must finish before
the next is submitted. Override `--partition`, `--time`, `--mem`, `--cpus`,
`--module`, `--conda-env` and `--mail-user` for the target cluster.

For local or dedicated-worker execution use
`python Tasks/prepare-code-smell-dataset/run_task.py` with the same stage
arguments; source stages then require `--source`.

Optional `--prior-manifest /external/prior.json` on `audit` accepts a JSON
object keyed by source, with absolute file paths:

```json
{
  "Apache": {
    "raw_jsonl": "/external/prior/raw_issues.jsonl",
    "field_map": "/external/prior/field_map.json",
    "features": "/external/prior/features.csv",
    "split": "/external/prior/split.json"
  }
}
```

`raw_jsonl`/`field_map` and `features`/`split` are paired, optional imports.
Use the existing Jira pipeline raw-record/field-map schema and this runtime's
split schema. Imports are hashed and rechecked; incompatible features or
membership cause an error, not a silently substituted split.

## Evidence and failures

Concrete GitHub merged PRs and commits reachable from default-branch history
are supported. PRs use their pinned merged head and changed-file inventory;
commits use the first-parent diff. Full snapshots preserve project context,
but labels apply only to associated changed `.java`, `.py` and `.cs` files.
Added and renamed files retain their post-change paths; deleted files cannot
produce post-change labels. Multiple revisions are not a consolidated latest
state or an introduced-smell experiment.

GitHub access uses `GITHUB_TOKEN` when supplied. Jira authentication follows
the reused `jira_pipeline.client` environment-variable contract. Do not place
tokens in task arguments, profiles or committed files.

Unavailable Jira records stop enrichment after recording failures; rerun after
restoring access. Evidence failures and unsupported links are explicitly
recorded, not labeled clean. Read the exclusion ledger before accepting cohort
retention. Detection incompleteness is a separate hard gate in the next task.

## Outputs and restart

Study artifacts live in `$STORAGE/runs/$RUN`: cohort snapshots, per-source raw
records and features, immutable split manifests, evidence manifests and
exclusion/overlap audits. Shared snapshots and tool caches also stay outside
Git. Task-owned `cluster_runs/<submission>/` contains `job_plan.json`,
`submitted_jobs.tsv`, and separate `logs/job-<job>_<array>.out/.err`.

Inspect study `status/*.json` and stage artifacts, not just scheduler exit
status. Rerun the same stage to reuse verified artifacts; changed code, cohort,
features, partitions or profiles require a new study ID. Never edit hashes to
force a resume. Full collection and snapshot acquisition are user-operated
runtime work, not performed by the offline regression tests.
