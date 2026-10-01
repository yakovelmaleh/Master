# Research HF instability models

| Item | This task |
| --- | --- |
| Research question | Can semantic text models improve within-project unstable-story prediction? |
| Training data | None: model research and hardware/profile preparation. |
| Split | The following training task preserves #357's historical per-project 60/20/20 split. |
| Models | ModernBERT-base, Qwen3-Embedding-0.6B, Qwen3.5-4B, Phi-4-mini-instruct, Gemma-4-E2B-it. |
| Coverage | Compatibility must be measured separately for each selected model and GPU configuration. |
| Results | Hardware inventory and load/train/save/reload profile, not prediction claims. |
| Completed outputs | Code and pinned model registry; no cluster measurements or model downloads are included. |

## Shortlist and resources

Official cards and revision metadata were reviewed October 1, 2026. `models.json`
pins exact commits; nothing follows a moving `main` at runtime. There is no
evidence yet that one candidate is best for this dataset. Begin with the compact
encoder/embedding models; the three larger decoder/multimodal candidates are
explicit opt-ins after profiling.

| Model | Rationale | Approximate BF16 weight bytes only | Unmeasured initial GPU envelope |
| --- | --- | --- | --- |
| ModernBERT-base, 149M | Bidirectional classification encoder; semantic baseline missing from current refactored models | 0.30 GB | 16-24 GiB |
| Qwen3-Embedding-0.6B | Frozen text representations with a small trainable head | 1.2 GB | 12-24 GiB |
| Phi-4-mini-instruct, 3.8B | Compact decoder with language-only LoRA classification | 7.6 GB | 24-48 GiB |
| Qwen3.5-4B | Alternative pretrained family; hybrid/multimodal compatibility gate | About 8 GB for language parameters | 24-48 GiB |
| Gemma-4-E2B-it | Alternative family; E2B does not mean a 2B stored checkpoint | At least 10.2 GB for 5.1B including embeddings | 24-48 GiB or more |

These are **estimates, not guarantees**. Training adds activations, optimizer,
adapter/head states and possibly modality components. Host `--mem` is not VRAM.
Large models use NF4 QLoRA; unsupported loading, dtype, quantization or language-only
adapter targets fail explicitly. A maximum-length forward/backward/optimizer and
adapter reload profile must succeed before training on the same GPU model and
environment. No automatic CPU fallback, FlashAttention assumption or OOM retry.
ModernBERT-large is a possible later expansion, not part of the initial grid.

## Runtime commands

Use the root instructions in `../train-hf-instability-within-project/README.md`
to create the isolated `master-hf` environment and prepare the shared cache.
All storage paths below are examples to replace with your cluster's persistent
storage. Partition/GRES must be confirmed locally.

```bash
bash Tasks/run_cluster_task.sh research-hf-instability-models \
  --stage probe --partition YOUR_CPU_PARTITION \
  --cache /cluster/storage/master-hf/cache --storage /cluster/storage/master-hf

bash Tasks/run_cluster_task.sh research-hf-instability-models \
  --stage profile --models modernbert \
  --partition YOUR_GPU_PARTITION --gres gpu:YOUR_TYPE:1 \
  --cache /cluster/storage/master-hf/cache --storage /cluster/storage/master-hf
```

Repeat the profile explicitly for each model you intend to use. Only one profile
job may be submitted at once. Use `--dry-run` to print sbatch without any download,
submission or runtime-directory creation. `--config` selects a documented
configuration, including dtype/sequence length; changing it requires re-profiling.

Files: `models.json` is the registry; `probe.py` records site capabilities;
`cluster/submit_jobs.sh` delegates to the shared launcher. Logs and array-index
mapping are under this task's `cluster_runs/<submission-id>/`; large profile
checkpoints and measurements are outside Git at
`<storage>/profiles/<model>/<config-hash>/`. Failure remains visible in sbatch logs.

## Primary sources

- https://huggingface.co/answerdotai/ModernBERT-base
- https://huggingface.co/Qwen/Qwen3-Embedding-0.6B
- https://huggingface.co/Qwen/Qwen3.5-4B
- https://huggingface.co/microsoft/Phi-4-mini-instruct
- https://huggingface.co/google/gemma-4-E2B-it
- https://huggingface.co/docs/peft/developer_guides/quantization
- https://slurm.schedmd.com/gres.html
