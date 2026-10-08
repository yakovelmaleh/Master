#!/usr/bin/env python3
"""Submit the separate local Jev task without changing existing HF profile hashes."""

import argparse
from pathlib import Path
import shlex
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jev_backend import TASK
from common import PROJECTS, REPO, exclusive_lock, external_path, slug, write_json


def directive(value):
    if not value or any(c.isspace() for c in value) or "#" in value:
        raise ValueError("Invalid SLURM directive value.")
    return value


def build_commands(args, run_root):
    if args.stage == "setup":
        return [["python", "-m", "pip", "install", "-r", str(TASK / "requirements.txt")],
                ["python", "-m", "pip", "check"]]
    base = ["python", "-u", str(TASK / "run_evaluation.py"), args.stage,
            "--cache", str(args.cache), "--storage", str(args.storage), "--run-id", args.run_id]
    if args.stage == "report":
        return [base + ["--report-output", str(run_root / "results/hf_report.json")]]
    if args.stage in ("validate", "test"):
        return [base + ["--project", name] for name in PROJECTS]
    return [base]


def render(args, run_root, commands):
    gpu = args.stage in ("profile", "validate", "test")
    if gpu and (not args.gres or not args.gres.startswith("gpu:") or args.gres.split(":")[-1] != "1"):
        raise ValueError("GPU stages require exactly one site-verified GPU, e.g. --gres gpu:rtx_3090:1.")
    count = 6 if args.stage in ("validate", "test") else 1
    lines = [
        "#!/usr/bin/env bash", f"#SBATCH --job-name=master-hf-jev-{args.stage}",
        "#SBATCH --partition=" + directive(args.partition),
        "#SBATCH --time=" + directive(args.time), "#SBATCH --mem=" + directive(args.mem),
        "#SBATCH --ntasks=1", "#SBATCH --cpus-per-task=6",
        f"#SBATCH --array=0-{count - 1}%{min(count, 2)}",
        "#SBATCH --output=" + directive(str(run_root / "logs/slurm-%A_%a.out")),
        "#SBATCH --error=" + directive(str(run_root / "logs/slurm-%A_%a.err")),
        "#SBATCH --mail-user=" + directive(args.mail_user), "#SBATCH --mail-type=ALL",
    ]
    if gpu:
        lines.append("#SBATCH --gres=" + directive(args.gres))
    lines.extend([
        "set -euo pipefail", "cd " + shlex.quote(str(REPO)),
        'echo "SLURM_JOB_ID=${SLURM_JOB_ID} ARRAY_TASK=${SLURM_ARRAY_TASK_ID}"',
        "date -u", "module load anaconda", "source activate " + shlex.quote(args.conda_env),
        "export PYTHONUNBUFFERED=1",
    ])
    if args.stage not in ("setup", "prepare"):
        lines.extend(["export HF_HUB_OFFLINE=1", "export TRANSFORMERS_OFFLINE=1"])
    lines.append('case "${SLURM_ARRAY_TASK_ID}" in')
    batches = [commands] if args.stage == "setup" else [[command] for command in commands]
    for index, batch in enumerate(batches):
        command = " && ".join(shlex.join(item) for item in batch)
        lines.append(f"  {index}) echo {shlex.quote(command)}; {command} ;;")
    lines.extend(['  *) echo "Invalid array index" >&2; exit 2 ;;', "esac", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, choices=("setup", "prepare", "profile", "validate", "seal", "test", "report"))
    parser.add_argument("--partition", required=True)
    parser.add_argument("--gres")
    parser.add_argument("--cache", required=True)
    parser.add_argument("--storage", required=True)
    parser.add_argument("--run-id", default="jev-study-01")
    parser.add_argument("--time", default="04:00:00")
    parser.add_argument("--mem", default="32G")
    parser.add_argument("--conda-env", default="master-hf")
    parser.add_argument("--mail-user", default="yakovelm@post.bgu.ac.il")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    args.run_id = slug(args.run_id)
    args.cache, args.storage = external_path(args.cache), external_path(args.storage)
    submission = f"{args.run_id}-{args.stage}-{uuid.uuid4().hex[:8]}"
    root = TASK / "cluster_runs" / submission
    commands = build_commands(args, root)
    text = render(args, root, commands)
    if args.dry_run:
        print(text)
        return
    with exclusive_lock(Path.home() / ".cache/master-hf/submission.lock"):
        active = subprocess.check_output(["squeue", "--me", "--noheader", "--format=%j"], text=True)
        if any(name.strip().startswith("master-hf-") for name in active.splitlines()):
            raise ValueError("Another Master HF job is active. Wait before submitting this stage.")
        root.mkdir(parents=True, exist_ok=False)
        (root / "logs").mkdir()
        (root / "results").mkdir()
        (root / "submit.sbatch").write_text(text)
        plan = {"schema": "hf-runtime-jobs-v1", "stage": args.stage, "run_id": args.run_id,
                "commands": commands, "status": "submitting", "storage": str(args.storage)}
        write_json(root / "hf_job_plan.json", plan)
        try:
            job_id = subprocess.check_output(["sbatch", "--parsable", str(root / "submit.sbatch")],
                                             text=True).strip().split(";")[0]
            if not job_id.isdigit():
                raise ValueError("Unrecognized sbatch result; check squeue before resubmitting.")
        except (subprocess.CalledProcessError, ValueError):
            write_json(root / "hf_job_plan.json", {**plan, "status": "submission_unconfirmed"})
            raise
        write_json(root / "hf_job_plan.json", {**plan, "status": "submitted", "job_id": job_id})
        (root.parent / "latest_run.txt").write_text(submission + "\n")
        print(f"Submitted {job_id}. Logs: {root / 'logs'}. Results: {args.storage / 'jev-runs' / args.run_id}")


if __name__ == "__main__":
    main()
