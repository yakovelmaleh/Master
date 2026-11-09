#!/usr/bin/env python3
"""One CPU-only milestone job; shares the existing global HF submission lock."""

import argparse
from pathlib import Path
import shlex
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from support import TASK, REPO, digest, exclusive_lock, external_path, file_hash, read_json, slug, write_json


def directive(value):
    if not value or any(c.isspace() for c in value) or "#" in value:
        raise ValueError("SLURM directive must not contain whitespace or '#'.")
    return value


def command_for(args, config_path):
    command = ["python", "-u", str(TASK / "scripts/run_diagnostics.py"),
               "--stage", args.stage, "--run-id", args.run_id,
               "--output-root", str(args.output_root), "--config", str(config_path)]
    for root in args.artifact_root or []:
        command.extend(["--artifact-root", str(root)])
    if args.histories:
        command.extend(["--histories", str(args.histories)])
    if args.tokenizer_cache:
        command.extend(["--tokenizer-cache", str(args.tokenizer_cache)])
    if args.reviews:
        command.extend(["--reviews", str(external_path(args.reviews))])
    return command


def render(args, root, command):
    lines = [
        "#!/usr/bin/env bash", f"#SBATCH --job-name=master-hf-diagnose-{args.stage}",
        "#SBATCH --partition=" + directive(args.partition),
        "#SBATCH --time=" + directive(args.time), "#SBATCH --mem=" + directive(args.mem),
        "#SBATCH --ntasks=1", f"#SBATCH --cpus-per-task={args.cpus}",
        "#SBATCH --array=0-0%1",
        "#SBATCH --output=" + directive(str(root / "logs/slurm-%A_%a.out")),
        "#SBATCH --error=" + directive(str(root / "logs/slurm-%A_%a.err")),
        "#SBATCH --mail-user=" + directive(args.mail_user), "#SBATCH --mail-type=ALL",
        "set -euo pipefail", "umask 077", "cd " + shlex.quote(str(REPO)),
        'echo "SLURM_JOB_ID=${SLURM_JOB_ID} ARRAY_TASK=${SLURM_ARRAY_TASK_ID}"',
        "date -u", "module load " + shlex.quote(args.module),
        "source activate " + shlex.quote(args.conda_env),
        "export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false",
        f"export OMP_NUM_THREADS={args.cpus} OPENBLAS_NUM_THREADS={args.cpus} MKL_NUM_THREADS={args.cpus}",
        "export PYTHONDONTWRITEBYTECODE=1",
        shlex.join(command), "",
    ]
    return "\n".join(lines)


def submit(args):
    from run_diagnostics import validate_config

    args.run_id = slug(args.run_id)
    if args.cpus < 1:
        raise ValueError("--cpus must be positive.")
    args.output_root = external_path(args.output_root)
    args.artifact_root = [external_path(p) for p in args.artifact_root or []]
    args.histories = external_path(args.histories) if args.histories else None
    args.tokenizer_cache = external_path(args.tokenizer_cache) if args.tokenizer_cache else None
    config = read_json(args.config)
    validate_config(config)
    submission = f"{args.run_id}-{args.stage}-{uuid.uuid4().hex[:8]}"
    root = TASK / "cluster_runs" / submission
    command = command_for(args, root / "configuration.json")
    text = render(args, root, command)
    if args.dry_run:
        # A dry-run is runnable without creating a submission directory/config.
        print(render(args, root, command_for(args, args.config.resolve())))
        return
    with exclusive_lock(Path.home() / ".cache/master-hf/submission.lock"):
        active = subprocess.check_output(
            ["squeue", "--me", "--noheader", "--format=%j"], text=True
        )
        if any(name.strip().startswith("master-hf-") for name in active.splitlines()):
            raise ValueError("Another Master HF job is active; wait before submitting diagnostics.")
        root.mkdir(parents=True, exist_ok=False)
        (root / "logs").mkdir()
        write_json(root / "configuration.json", config)
        (root / "submit.sbatch").write_text(text)
        plan = {
            "schema": "instability-diagnostics-jobs-v1", "run_id": args.run_id,
            "stage": args.stage, "status": "submitting", "command": command,
            "configuration_sha256": digest(config), "launcher_sha256": file_hash(Path(__file__)),
            "outputs": str(args.output_root / args.run_id),
            "stage_job_mapping": [{"array_index": 0, "stages": (
                ["T1", "T2", "T3"] if args.stage == "milestone1" else
                [{"inventory": "T1", "profile": "T2", "errors": "T3"}[args.stage]]
            )}],
            "stdout": str(root / "logs/slurm-%A_%a.out"),
            "stderr": str(root / "logs/slurm-%A_%a.err"),
        }
        write_json(root / "job_manifest.json", plan)
        try:
            job_id = subprocess.check_output(
                ["sbatch", "--parsable", str(root / "submit.sbatch")], text=True
            ).strip().split(";")[0]
            if not job_id.isdigit():
                raise ValueError("Unrecognized sbatch response; check squeue before retrying.")
        except (subprocess.CalledProcessError, ValueError, OSError):
            write_json(root / "job_manifest.json", {**plan, "status": "submission_unconfirmed"})
            raise
        write_json(root / "job_manifest.json", {**plan, "status": "submitted", "job_id": job_id,
                   "stage_job_mapping": [{**m, "job_id": job_id + "_0"} for m in plan["stage_job_mapping"]]})
        (root.parent / "latest_run.txt").write_text(submission + "\n")
        print(f"Submitted {job_id}; job manifest: {root / 'job_manifest.json'}")
        print(f"stdout: {root / 'logs' / ('slurm-' + job_id + '_0.out')}")
        print(f"stderr: {root / 'logs' / ('slurm-' + job_id + '_0.err')}")
        print(f"External artifacts: {args.output_root / args.run_id}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, choices=("inventory", "profile", "errors", "milestone1"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--partition", required=True)
    parser.add_argument("--output-root", type=Path, default=Path.home() / "master-hf/diagnostics")
    parser.add_argument("--artifact-root", type=Path, action="append")
    parser.add_argument("--histories", type=Path)
    parser.add_argument("--tokenizer-cache", type=Path)
    parser.add_argument("--reviews", type=Path)
    parser.add_argument("--config", type=Path, default=TASK / "configuration/milestone1.json")
    parser.add_argument("--mem", default="16G")
    parser.add_argument("--cpus", type=int, default=4)
    parser.add_argument("--time", default="02:00:00")
    parser.add_argument("--module", default="anaconda")
    parser.add_argument("--conda-env", default="master-hf")
    parser.add_argument("--mail-user", default="yakovelm@post.bgu.ac.il")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        submit(args)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"{exc}\n")


if __name__ == "__main__":
    main()
