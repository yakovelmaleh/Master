# Explicit private HF publication

| Item | This task |
| --- | --- |
| Research question | Can the selected classifier be reloaded from an immutable private artifact? |
| Training data | None is uploaded. Local validation rows are used only for reload comparison. |
| Split | No retraining or reselection; the source study must be sealed. |
| Models | One explicitly selected head and, when applicable, its LoRA adapter. |
| Coverage | Allowlisted deployment files, private destination, hashes and prediction equivalence. |
| Results | Private HF commit reference in the external study's `publications/`. |
| Completed outputs | Publishing code only; no model has been published by this change. |

Publishing is optional and never happens automatically during training. Configure
your namespace and secure cluster authentication first. Review checkpoint/data-export
permissions and the pinned base model's license, then explicitly approve export.
Private publication is not permission to publish raw Jira content or secrets.

```bash
bash Tasks/run_cluster_task.sh publish-hf-instability-models \
  --checkpoint /cluster/storage/master-hf/runs/RUN/frozen/PROJECT/MODEL/LEVEL/CANDIDATE/checkpoint \
  --hf-repo YOUR_NAMESPACE/YOUR_PRIVATE_MODEL --approve-export \
  --partition YOUR_GPU_NETWORK_ENABLED_PARTITION --gres gpu:YOUR_TYPE:1 \
  --cache /cluster/storage/master-hf/cache --storage /cluster/storage/master-hf
```

Reloading needs the same model's inference resources; use the direct Python
command inside an appropriately allocated GPU/network-enabled job if the site
separates GPU and publishing nodes:

```bash
python Tasks/publish-hf-instability-models/publish_model.py \
  --checkpoint /path/to/selected/checkpoint --repo-id YOUR_NAMESPACE/YOUR_PRIVATE_MODEL \
  --storage /cluster/storage/master-hf --cache /cluster/storage/master-hf/cache \
  --approve-export
```

`publish_model.py` creates private repositories and rejects an existing public
destination **before uploading**. It only accepts a sealed selection and rejects
unknown deployment files. Tokenizer/base weights remain referenced by immutable
revision rather than being duplicated. No raw data, predictions, logs, cache,
optimizer state or credentials are uploaded.

After uploading, it verifies privacy again, checks the remote commit's file hashes,
loads a new model instance and checks validation prediction equivalence. An
exception means publication verification is incomplete; inspect the destination,
do not assume rollback. Hub permissions must prevent unauthorized concurrent
privacy changes. The runtime output records the private repo ID and exact commit.

Source: https://huggingface.co/docs/huggingface_hub/guides/upload
