#!/usr/bin/env python3
"""Render or submit bounded SLURM jobs; never download model weights on submission."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import shlex
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import (
    PROJECTS, REPO, TASK, digest, exclusive_lock, external_path,
    model_registry, read_json, slug, write_json,
)


TASKS = {
    "research": "research-hf-instability-models",
    "prepare": "prepare-hf-instability-models",
    "train": "train-hf-instability-within-project",
    "publish": "publish-hf-instability-models",
}


def clean_directive(value):
    if not value or any(c.isspace() for c in value) or "#" in value:
        raise ValueError("SLURM directive values must be nonempty and contain no whitespace or '#'.")
    return value


def render(args, run_root, commands, config):
    gpu = args.kind == "publish" or args.kind in ("research", "train") and args.stage not in ("seal", "report", "probe")
    if gpu and not args.gres:
        raise ValueError("GPU jobs require a site-verified --gres, for example gpu:a100:1.")
    if args.gres and (not args.gres.startswith("gpu:") or args.gres.split(":")[-1] != "1"):
        raise ValueError("Each job must request exactly one GPU.")
    if args.kind == "research" and args.stage == "profile" and len(commands) != 1:
        raise ValueError("Profile exactly one model first; repeat explicitly for additional models.")
    concurrent = 1 if args.kind == "research" else min(2, len(commands))
    lines = [
        "#!/usr/bin/env bash", "#SBATCH --job-name=master-hf-" + args.kind,
        "#SBATCH --partition=" + clean_directive(args.partition),
        "#SBATCH --time=" + clean_directive(args.time),
        "#SBATCH --mem=" + clean_directive(args.mem),
        "#SBATCH --ntasks=1", f"#SBATCH --cpus-per-task={args.cpus}",
        f"#SBATCH --array=0-{len(commands)-1}%{concurrent}",
        "#SBATCH --output=" + clean_directive(str(run_root / "logs/slurm-%A_%a.out")),
        "#SBATCH --error=" + clean_directive(str(run_root / "logs/slurm-%A_%a.err")),
    ]
    if gpu:
        lines.append("#SBATCH --gres=" + clean_directive(args.gres))
    if args.mail_user:
        lines.extend(["#SBATCH --mail-user=" + clean_directive(args.mail_user), "#SBATCH --mail-type=ALL"])
    lines.extend([
        "set -euo pipefail",
        "cd " + shlex.quote(str(REPO)),
        'echo "SLURM_JOB_ID=${SLURM_JOB_ID} ARRAY_TASK=${SLURM_ARRAY_TASK_ID}"',
        "date -u",
        "module load " + shlex.quote(args.module),
        "source activate " + shlex.quote(args.conda_env),
    ])
    if args.kind == "train" or args.kind == "research" and args.stage == "profile":
        lines.extend(["export HF_HUB_OFFLINE=1", "export TRANSFORMERS_OFFLINE=1"])
    lines.append('case "${SLURM_ARRAY_TASK_ID}" in')
    for index, command in enumerate(commands):
        label = shlex.quote(f"Task {index}: {shlex.join(command)}")
        lines.append(f"  {index}) echo {label}; {shlex.join(command)} ;;")
    lines.extend(['  *) echo "Invalid array index" >&2; exit 2 ;;', "esac", ""])
    return "\n".join(lines)


def commands_for(args, config_path):
    if args.kind == "prepare":
        return [["python", str(REPO / "Tasks/prepare-hf-instability-models/prepare_models.py"),
                 "--cache", str(args.cache), "--models", *args.models] + (["--offline"] if args.offline else [])]
    if args.kind == "research" and args.stage == "probe":
        return [["python", str(REPO / "Tasks/research-hf-instability-models/probe.py"),
                 "--output", str(args.storage / "hardware.json")]]
    if args.kind == "publish":
        if not args.checkpoint or not args.hf_repo or not args.approve_export:
            raise ValueError("Publishing requires --checkpoint, --hf-repo and --approve-export.")
        return [["python", str(REPO / "Tasks/publish-hf-instability-models/publish_model.py"),
                 "--checkpoint", str(external_path(args.checkpoint)), "--repo-id", args.hf_repo,
                 "--cache", str(args.cache), "--storage", str(args.storage), "--approve-export"]]
    base = ["python", str(TASK / "run_experiment.py"), args.stage,
            "--cache", str(args.cache), "--storage", str(args.storage),
            "--config", str(config_path), "--run-id", args.run_id, "--models", *args.models]
    if args.stage in ("seal", "report"):
        return [base + ["--report-output", str(REPO / "Tasks" / TASKS[args.kind] /
                                             "cluster_runs" / args.submission_id / "results/hf_report.json")]]
    if args.stage == "profile":
        return [base + ["--model", name] for name in args.models]
    return [base + ["--project", project, "--model", name] for project in PROJECTS for name in args.models]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=TASKS)
    parser.add_argument("--stage", choices=("probe", "profile", "frozen", "finetune", "seal", "test", "report"))
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--storage", type=Path, required=True)
    parser.add_argument("--models", nargs="+", choices=sorted(model_registry()), default=["modernbert", "qwen_embedding"])
    parser.add_argument("--run-id")
    parser.add_argument("--partition", required=True)
    parser.add_argument("--gres")
    parser.add_argument("--mem", default="32G")
    parser.add_argument("--cpus", type=int, default=6)
    parser.add_argument("--time", default="1-00:00:00")
    parser.add_argument("--conda-env", default="master-hf")
    parser.add_argument("--module", default="anaconda")
    parser.add_argument("--mail-user")
    parser.add_argument("--config", type=Path, default=TASK / "experiment.json")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--hf-repo")
    parser.add_argument("--approve-export", action="store_true")
    args = parser.parse_args()
    if args.cpus < 1:
        raise ValueError("--cpus must be positive.")
    allowed = {"research": ("probe", "profile"), "train": ("frozen", "finetune", "seal", "test", "report"),
               "prepare": (None,), "publish": (None,)}
    if args.stage not in allowed[args.kind]:
        raise ValueError(f"Select a valid --stage for {args.kind}: {allowed[args.kind]}")
    if args.kind == "train" and not args.run_id:
        raise ValueError("--run-id is required for all stages of the same training study.")
    args.run_id = slug(args.run_id or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))
    args.submission_id = args.run_id + "-" + (args.stage or args.kind) + "-" + uuid.uuid4().hex[:8]
    args.cache, args.storage = external_path(args.cache), external_path(args.storage)
    root = REPO / "Tasks" / TASKS[args.kind] / "cluster_runs" / args.submission_id
    config = read_json(args.config)
    commands = commands_for(args, root / "experiment.json")
    text = render(args, root, commands, config)
    if args.dry_run:
        print(text)
        return
    # Serialize all Master HF submissions for this user, even across storage roots.
    with exclusive_lock(Path.home() / ".cache/master-hf/submission.lock"):
        active = subprocess.check_output(
            ["squeue", "--me", "--noheader", "--format=%j"], text=True
        ).splitlines()
        if any(name.strip().startswith("master-hf-") for name in active):
            raise ValueError("Another Master HF array is active. Wait for completion before the next submission.")
        root.mkdir(parents=True, exist_ok=False)
        (root / "logs").mkdir()
        (root / "results").mkdir()
        write_json(root / "experiment.json", config)
        (root / "submit.sbatch").write_text(text)
        manifest = {"schema": "hf-runtime-jobs-v1", "status": "submitting", "run_id": args.run_id,
                    "kind": args.kind, "stage": args.stage, "commands": commands,
                    "config_sha256": digest(config), "storage": str(args.storage),
                    "logs": "logs/slurm-<array>_<index>.out"}
        write_json(root / "hf_job_plan.json", manifest)
        try:
            job_id = subprocess.check_output(
                ["sbatch", "--parsable", str(root / "submit.sbatch")], text=True
            ).strip().split(";")[0]
        except subprocess.CalledProcessError:
            write_json(root / "hf_job_plan.json", {**manifest, "status": "submission_failed"})
            raise
        if not job_id.isdigit():
            raise ValueError("Unrecognized sbatch response. Check squeue before retrying submission.")
        write_json(root / "hf_job_plan.json", {**manifest, "status": "submitted", "job_id": job_id})
        (root.parent / "latest_run.txt").write_text(args.submission_id + "\n")
        print(f"Submitted {job_id}. Logs: {root / 'logs'}. Study: {args.storage / 'runs' / args.run_id}")


if __name__ == "__main__":
    main()
