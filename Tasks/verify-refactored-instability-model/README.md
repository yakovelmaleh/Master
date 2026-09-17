# Verify the refactored instability model

This task runs the refactored weighted instability model on the same existing
processed CSV datasets. It does not download Jira issues and does not compare
the refactored outputs with the original model outputs.

The comparison will be implemented as a separate task and pull request.

## Input datasets

`datasets.json` explicitly lists the six existing datasets:

```text
Data/Apache/features_labels_table_os.csv
Data/Hyperledger/features_labels_table_os.csv
Data/IntelDAOS/features_labels_table_os.csv
Data/Jira/features_labels_table_os.csv
Data/MariaDB/features_labels_table_os.csv
Data/Qt/features_labels_table_os.csv
```

Paths are resolved from the repository root. The verification manifest records
the absolute path, byte size, and SHA-256 hash of every input. These
fingerprints will let the later comparison task prove that both model runs used
the same CSV files.

## Model being verified

The task calls the refactored model in:

```text
Tasks/jira-url-to-instability-model/unstable_model/
```

The model uses:

- Balanced class-based sample weights.
- Chronological 60/20/20 train, validation, and test splits.
- Validation-only threshold selection.
- L2 regularization and validation early stopping.
- Only features available at or before sprint entry.

The default target is `is_change_text_num_words_5`.

## Cluster run

From the repository root:

```bash
./Tasks/run_cluster_task.sh \
  --pull \
  verify-refactored-instability-model
```

`--pull` runs `git pull --ff-only` before the task is submitted. Omit it to use
the code currently checked out on the cluster.

The task submits one SLURM job that trains the combined `all` model using all
six configured datasets.

Run one dataset instead:

```bash
./Tasks/run_cluster_task.sh \
  verify-refactored-instability-model \
  --project Apache
```

Use another instability threshold:

```bash
./Tasks/run_cluster_task.sh \
  verify-refactored-instability-model \
  --label-threshold 10
```

## Validate before submitting

Generate and inspect the sbatch file without calling SLURM:

```bash
./Tasks/run_cluster_task.sh \
  verify-refactored-instability-model \
  --dry-run
```

Validate dataset paths and hashes without training:

```bash
python3 Tasks/verify-refactored-instability-model/run_verification.py \
  --validate-only
```

## Results and logs

Each invocation creates a timestamped task-owned folder:

```text
cluster_runs/<run-id>/
├── submitted_jobs.tsv
└── all/
    ├── submit.sbatch
    ├── logs/
    │   └── job-<SLURM_JOB_ID>.out
    └── results/
        ├── verification_manifest.json
        ├── input_layout/
        │   ├── Apache/features_labels_table_os.csv
        │   └── ...
        └── model/
            └── all_words_5/
                ├── model.npz
                ├── feature_transformer.json
                ├── metrics.json
                ├── run_metadata.json
                ├── validation_predictions.csv
                ├── test_predictions.csv
                ├── feature_coefficients.csv
                └── report.html
```

The files under `input_layout/` are symbolic links to the original datasets;
the CSV files are not copied or modified.

`verification_manifest.json` records the exact inputs, selected project,
label threshold, status, final metrics, and model output directory.

`submitted_jobs.tsv` maps the SLURM job ID to its results, `.out` log, and
generated sbatch file. `cluster_runs/latest_run.txt` contains the latest run
directory.

Generated `cluster_runs/` content is ignored by Git.

## Local run

Install the small dependency set:

```bash
python3 -m pip install -r \
  Tasks/verify-refactored-instability-model/requirements.txt
```

Then run:

```bash
python3 Tasks/verify-refactored-instability-model/run_verification.py
```

This performs only the refactored run. It intentionally makes no statement
about whether the original and refactored results match.
