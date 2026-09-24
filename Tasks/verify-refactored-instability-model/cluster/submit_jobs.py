#!/usr/bin/env python3
"""Generate a complete, task-owned job matrix before submitting any job."""

import argparse
import json
import re
import shlex
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


PROJECTS = ("Apache", "Hyperledger", "IntelDAOS", "Jira", "MariaDB", "Qt")
LEVELS = (5, 10, 15, 20)
SHARED_TASK = Path(__file__).resolve().parents[1]
REPO = SHARED_TASK.parents[1]


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--task-dir", type=Path, required=True)
    p.add_argument("--protocol", choices=["pooled", "within-project", "leave-one-project-out"], required=True)
    p.add_argument("--datasets-file", type=Path)
    p.add_argument("--project", choices=["all", *PROJECTS])
    p.add_argument("--only", choices=PROJECTS, action="append", default=[])
    p.add_argument("--label-threshold", choices=LEVELS, type=int, action="append")
    p.add_argument("--models", choices=["RF", "XGboost", "NN"], nargs="+", default=["RF", "XGboost", "NN"])
    p.add_argument("--comparison-config", type=Path, default=SHARED_TASK / "comparison_config.json")
    p.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    p.add_argument("--conda-env", default="master")
    p.add_argument("--partition", default="main")
    p.add_argument("--time", default="4-03:30:00")
    p.add_argument("--validate-only", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    return p


def submit(args):
    args.models = list(dict.fromkeys(args.models))
    task = args.task_dir.resolve()
    # Protocol/model selection is task-owned, not a user-overridable alias.
    task_modes = {
        "verify-refactored-instability-model": ("pooled", "comparison"),
        "validate-refactored-model-per-dataset": ("within-project", "comparison"),
        "compare-models-leave-one-project-out": ("leave-one-project-out", "comparison"),
        "evaluate-logistic-instability-model": ("pooled", "logistic"),
    }
    protocol, experiment = task_modes[task.name]
    if args.protocol != protocol:
        raise ValueError("Use the separate task for the requested protocol.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", args.run_id):
        raise ValueError("Invalid run ID.")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", args.partition) or not re.fullmatch(r"[0-9:-]+", args.time):
        raise ValueError("Invalid SLURM partition or time.")
    if not args.conda_env or "\n" in args.conda_env or "\r" in args.conda_env:
        raise ValueError("Invalid conda environment.")
    datasets_file = (args.datasets_file or task / "datasets.json").resolve()
    datasets = json.loads(datasets_file.read_text())
    if not isinstance(datasets, dict) or not datasets:
        raise ValueError("Datasets file must be a non-empty object.")
    for project, value in datasets.items():
        if project not in PROJECTS or not isinstance(value, str):
            raise ValueError(f"Invalid dataset entry: {project}")
        path = Path(value).expanduser()
        if not (path if path.is_absolute() else REPO / path).is_file():
            raise FileNotFoundError(f"Dataset missing: {value}")
    if args.only and args.project:
        raise ValueError("Use --only or --project, not both.")
    if protocol == "pooled":
        if args.only:
            raise ValueError("Pooled task uses --project, not --only.")
        projects = [args.project or "all"]
    else:
        projects = list(dict.fromkeys(args.only or ([args.project] if args.project else list(datasets))))
        if "all" in projects:
            raise ValueError("Use no project filter to submit all per-project jobs.")
    required = set(PROJECTS) if "all" in projects or protocol == "leave-one-project-out" else set(projects)
    if required - set(datasets):
        raise ValueError(f"Missing configured datasets: {sorted(required - set(datasets))}")
    if not args.dry_run and not shutil.which("sbatch"):
        raise RuntimeError("sbatch is required unless --dry-run is used.")
    config = json.loads(args.comparison_config.read_text())
    if not isinstance(config.get("seed"), int):
        raise ValueError("Comparison configuration requires an integer seed.")
    for model in args.models:
        if not config.get("models", {}).get(model):
            raise ValueError(f"No parameter candidates configured for {model}.")
    levels = sorted(set(args.label_threshold or LEVELS))
    models = args.models if experiment == "comparison" else ["Logistic"]
    variants = ["baseline", "refactored"] if experiment == "comparison" else ["logistic"]
    root = task / "cluster_runs" / args.run_id
    root.mkdir(parents=True, exist_ok=False)
    # Immutable copies prevent config edits after submission from changing a run.
    resolved_datasets = {
        name: str((Path(value).expanduser() if Path(value).expanduser().is_absolute()
                   else REPO / value).resolve()) for name, value in datasets.items()
    }
    (root / "datasets.json").write_text(json.dumps(resolved_datasets, indent=2) + "\n")
    (root / "comparison_config.json").write_text(json.dumps(config, indent=2) + "\n")
    jobs = []
    for project in projects:
        for level in levels:
            relative = Path(project.lower()) / f"words_{level}"
            job_root = root / relative
            results = job_root / "results"
            logs = job_root / "logs"
            results.mkdir(parents=True)
            logs.mkdir()
            command = [
                "python", str(SHARED_TASK / "run_verification.py"),
                "--datasets-file", str(root / "datasets.json"),
                "--comparison-config", str(root / "comparison_config.json"),
                "--protocol", protocol, "--experiment", experiment,
                "--project", project, "--label-threshold", str(level),
                "--models", *args.models, "--output-root", str(results),
            ]
            if args.validate_only:
                command.append("--validate-only")
            sbatch = job_root / "submit.sbatch"
            sbatch.write_text(
                "#!/bin/bash\n"
                f"#SBATCH --partition={args.partition}\n"
                f"#SBATCH --time={args.time}\n"
                f"#SBATCH --job-name={task.name[:35]}-{project.lower()}-k{level}\n"
                f"#SBATCH --output={logs}/job-%J.out\n"
                "#SBATCH --ntasks=1\n#SBATCH --cpus-per-task=6\n#SBATCH --mem=16G\n"
                "set -euo pipefail\n"
                'echo "SLURM_JOB_ID=${SLURM_JOB_ID:-unknown} NODE=${SLURM_JOB_NODELIST:-unknown}"\n'
                "module load anaconda\n"
                f"source activate {shlex.quote(args.conda_env)}\n"
                "export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-6}\n"
                "export OPENBLAS_NUM_THREADS=${SLURM_CPUS_PER_TASK:-6}\n"
                "export MKL_NUM_THREADS=${SLURM_CPUS_PER_TASK:-6}\n"
                f"cd {shlex.quote(str(REPO))}\n{shlex.join(command)}\n"
            )
            sbatch.chmod(0o755)
            jobs.append({
                "project": project, "level": level, "models": models, "variants": variants,
                "results": str(relative / "results"), "log": str(relative / "logs/job-%J.out"),
                "sbatch": str(relative / "submit.sbatch"), "job_id": "PENDING",
            })
    plan = {
        "task": task.name, "protocol": protocol, "experiment": experiment,
        "levels": levels, "models": models, "variants": variants,
        "validate_only": args.validate_only, "dry_run": args.dry_run, "jobs": jobs,
    }
    plan_path = root / "job_plan.json"

    def persist():
        plan_path.write_text(json.dumps(plan, indent=2) + "\n")
        with (root / "submitted_jobs.tsv").open("w") as manifest:
            manifest.write("project\tlevel\tjob_id\tresults\tlog\tsbatch\n")
            for job in jobs:
                manifest.write("\t".join(str(job[key]) for key in
                                         ("project", "level", "job_id", "results", "log", "sbatch")) + "\n")

    persist()
    (task / "cluster_runs/latest_run.txt").write_text(str(root) + "\n")
    for job in jobs:
        if args.dry_run:
            job["job_id"] = "DRY-RUN"
        else:
            try:
                response = subprocess.check_output(
                    ["sbatch", "--parsable", str(root / job["sbatch"])], text=True
                ).strip().split(";")[0]
                if not response.isdigit():
                    raise RuntimeError(f"Invalid sbatch job ID: {response!r}")
                job["job_id"] = response
            except Exception as error:
                job["job_id"] = "SUBMISSION-FAILED"
                plan["submission_error"] = str(error)
                persist()
                raise
        persist()
        print(f"{job['project']} level {job['level']}: {job['job_id']} -> {root / job['results']}")
    print(f"{len(jobs)} job(s). Run: {root}")


if __name__ == "__main__":
    arguments = parser().parse_args()
    try:
        submit(arguments)
    except (ValueError, KeyError, OSError, RuntimeError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"Submission failed: {error}")
