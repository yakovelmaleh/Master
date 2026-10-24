#!/usr/bin/env python3
"""Submit one resumable CPU stage; never allocate a GPU or resubmit implicitly."""

import argparse
from pathlib import Path
import shlex
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol import TASK, REPO, exclusive_lock, external_path, slug, write_json

STAGES = ("setup", "check-sdk", "prepare", "preflight", "smoke", "train-submit", "train-status", "reconcile",
          "validate", "seal", "test", "report", "cancel", "cleanup")


def directive(value):
    if not value or any(c.isspace() for c in value) or "#" in value:
        raise ValueError("Invalid SLURM directive.")
    return value


def commands(args, output):
    if args.stage == "setup":
        return [["python", "-c", "import sys; sys.exit(0 if sys.version_info[:2] == (3, 11) else 'Use a Python 3.11 environment; do not overwrite an existing environment.')"],
                ["python", "-m", "pip", "install", "-r", str(TASK / "requirements.txt")],
                ["python", "-m", "pip", "check"]]
    if args.stage == "check-sdk":
        return [
            ["python", "-m", "pip", "check"],
            ["python", str(TASK / "tests/check_installed_sdk.py")],
            ["python", "-m", "unittest", "discover", "-s", str(TASK / "tests"), "-q"],
            ["python", "-m", "unittest", "discover",
             "-s", str(TASK.parent / "create-task-summary-pr/tests"), "-q"],
            ["python", "-c", "print('SDK_OFFLINE_CHECKS_PASSED')"],
        ]
    command = ["python", "-u", str(TASK / "run_experiment.py"), args.stage,
               "--storage", str(args.storage), "--run-id", args.run_id, "--config", str(args.config)]
    if args.approval:
        command += ["--approval", str(args.approval)]
    if args.stage == "report":
        command += ["--report-output", str(output / "results/llm_report.json")]
    if args.delete_models:
        command.append("--delete-models")
    return [command]


def render(args, output, batch):
    lines = [
        "#!/usr/bin/env bash",
        "#SBATCH --job-name=master-openai-" + args.stage,
        "#SBATCH --partition=" + directive(args.partition),
        "#SBATCH --time=" + directive(args.time),
        "#SBATCH --mem=" + directive(args.mem),
        "#SBATCH --ntasks=1", "#SBATCH --cpus-per-task=2",
        "#SBATCH --output=" + directive(str(output / "logs/slurm-%j.out")),
        "#SBATCH --error=" + directive(str(output / "logs/slurm-%j.err")),
        "#SBATCH --mail-user=" + directive(args.mail_user), "#SBATCH --mail-type=ALL",
        "set -euo pipefail", "umask 077", "cd " + shlex.quote(str(REPO)),
        "module load anaconda",
    ]
    if args.stage == "setup":
        probe = (
            "import json,os,sys; paths=json.load(sys.stdin)['envs']; "
            "print('present' if any(os.path.basename(p)==sys.argv[1] for p in paths) else 'absent')"
        )
        lines.extend([
            "environment_state=$(conda env list --json | python -c "
            + shlex.quote(probe) + " " + shlex.quote(args.conda_env) + ")",
            'if [[ "$environment_state" == absent ]]; then',
            "  conda create --yes --name " + shlex.quote(args.conda_env) + " python=3.11",
            "fi",
        ])
    lines.extend([
        "source activate " + shlex.quote(args.conda_env),
        "export PYTHONUNBUFFERED=1",
        " && ".join(shlex.join(command) for command in batch), "",
    ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=STAGES, required=True)
    parser.add_argument("--storage", required=True)
    parser.add_argument("--run-id", default="openai-qt-jira-cloud-01")
    parser.add_argument("--partition", required=True)
    parser.add_argument("--time", default="04:00:00")
    parser.add_argument("--mem", default="8G")
    parser.add_argument("--conda-env", default="master-openai")
    parser.add_argument("--mail-user", default="yakovelm@post.bgu.ac.il")
    parser.add_argument("--config", type=Path, default=TASK / "experiment.json")
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--delete-models", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    args.storage, args.run_id = external_path(args.storage), slug(args.run_id)
    args.conda_env = slug(args.conda_env)
    args.config = args.config.expanduser().resolve()
    if args.approval:
        if args.stage != "preflight":
            parser.error("--approval is valid only for preflight")
        args.approval = external_path(args.approval)
    if args.stage == "preflight" and args.approval is None:
        parser.error("preflight requires a reviewed external --approval")
    if args.delete_models and args.stage != "cleanup":
        parser.error("--delete-models is valid only for explicit cleanup")
    root = TASK / "cluster_runs" / f"{args.run_id}-{args.stage}-{uuid.uuid4().hex[:8]}"
    batch = commands(args, root)
    script = render(args, root, batch)
    if args.dry_run:
        print(script)
        return
    with exclusive_lock(Path.home() / ".local/state/master-openai/.submission.lock"):
        names = subprocess.check_output(["squeue", "--me", "--noheader", "--format=%j"], text=True)
        if any(name.startswith("master-openai-") for name in names.splitlines()):
            raise ValueError("A Master OpenAI CPU stage is already active.")
        root.mkdir(parents=True, exist_ok=False)
        (root / "logs").mkdir()
        (root / "results").mkdir()
        (root / "submit.sbatch").write_text(script)
        plan = {"schema": "openai-cluster-jobs-v1", "stage": args.stage, "run_id": args.run_id,
                "commands": batch, "status": "submission_unconfirmed"}
        write_json(root / "llm_job_plan.json", plan)
        job_id = subprocess.check_output(["sbatch", "--parsable", str(root / "submit.sbatch")],
                                         text=True).strip().split(";")[0]
        if not job_id.isdigit():
            raise ValueError("Submission unconfirmed; inspect squeue before retrying.")
        write_json(root / "llm_job_plan.json", {**plan, "status": "submitted", "job_id": job_id})
        print(f"Submitted CPU job {job_id}. Logs: {root / 'logs'}")


if __name__ == "__main__":
    main()
