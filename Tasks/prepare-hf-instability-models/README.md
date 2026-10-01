# Prepare models at runtime

| Item | This task |
| --- | --- |
| Research question | Can the selected pinned model be acquired reproducibly on the cluster? |
| Training data | None. No Jira data is sent to Hugging Face. |
| Split | None; this is runtime preparation, not evaluation. |
| Models | Explicit `--models` selection from the research registry. |
| Coverage | Exact model/tokenizer revision and all necessary safetensors shards. |
| Results | External shared cache and readiness/hash manifest. |
| Completed outputs | Download/preflight code only; no pretrained weights in Git. |

`prepare_models.py` calls `snapshot_download` **only when invoked at runtime**.
Importing modules, rendering sbatch, reviewing a PR and running offline tests do
not fetch weights. Use storage outside the repository; cache snapshots are reused
across repositories and levels. Keep this storage available to every compute node.

```bash
bash Tasks/run_cluster_task.sh prepare-hf-instability-models \
  --models modernbert qwen_embedding \
  --partition YOUR_NETWORK_ENABLED_PARTITION \
  --cache /cluster/storage/master-hf/cache --storage /cluster/storage/master-hf
```

Alternatively run the Python command directly in the isolated environment on an
approved network-enabled node:

```bash
python Tasks/prepare-hf-instability-models/prepare_models.py \
  --cache /cluster/storage/master-hf/cache --models modernbert qwen_embedding
```

Wait for successful preparation before profiling/training. GPU jobs are offline;
missing or corrupt files fail instead of downloading unexpectedly. `--offline`
checks already cached snapshots. The cache root contains `ready/<model>.json`
with exact revisions and file hashes. Hub cache locking protects overlapping
snapshot downloads; model loading verifies file hashes.

Configure required HF authentication through the cluster's approved secret
mechanism; never add tokens to source, CLI arguments or generated sbatch files.
Check model access/license terms before preparing gated revisions. Disk estimates
are conservative; existing cache content may reduce actual download size.
Logs and submission metadata live in this task's ignored `cluster_runs/`.

Reference: https://huggingface.co/docs/huggingface_hub/guides/download
