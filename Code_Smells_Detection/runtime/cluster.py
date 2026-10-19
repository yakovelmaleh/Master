"""Nonblocking, bounded SLURM submission with task-owned logs and explicit stages."""

from datetime import datetime, timezone
from pathlib import Path
import shlex
import subprocess
import uuid

from .cli import SOURCE_STAGES, STAGES, parser, validate_arguments
from .common import REPO, TASKS, file_hash, identifier, lock, read_json, study, verify_study, write_json


def directive(value):
    value = str(value)
    if not value or any(char.isspace() for char in value) or "#" in value:
        raise ValueError("SLURM directive values must be nonempty and whitespace-free.")
    return value


def render(args, commands, run_root):
    output = [
        "#!/usr/bin/env bash", "#SBATCH --job-name=master-smells-" + args.kind,
        "#SBATCH --partition=" + directive(args.partition),
        "#SBATCH --time=" + directive(args.time), "#SBATCH --mem=" + directive(args.mem),
        "#SBATCH --ntasks=1", "#SBATCH --cpus-per-task=" + str(args.cpus),
        f"#SBATCH --array=0-{len(commands)-1}%{min(2, len(commands))}",
        "#SBATCH --output=" + directive(run_root / "logs/job-%A_%a.out"),
        "#SBATCH --error=" + directive(run_root / "logs/job-%A_%a.err"),
        "#SBATCH --mail-user=" + directive(args.mail_user), "#SBATCH --mail-type=ALL",
        "set -euo pipefail", "cd " + shlex.quote(str(REPO)),
        "module load " + shlex.quote(args.module),
        "source activate " + shlex.quote(args.conda_env),
        "export PYTHONUNBUFFERED=1",
        'echo "SLURM_JOB_ID=${SLURM_JOB_ID} ARRAY_TASK=${SLURM_ARRAY_TASK_ID}"',
        "date -u", 'case "${SLURM_ARRAY_TASK_ID}" in',
    ]
    for index, command in enumerate(commands):
        output.append(f"  {index}) echo {shlex.quote(shlex.join(command))}; {shlex.join(command)} ;;")
    output += ['  *) echo "Invalid array index" >&2; exit 2 ;;', "esac", ""]
    return "\n".join(output)


def main(kind):
    arguments = parser(kind)
    arguments.add_argument("--partition", default="main")
    arguments.add_argument("--time", default="1-00:00:00")
    arguments.add_argument("--mem", default="16G")
    arguments.add_argument("--cpus", type=int, default=6)
    arguments.add_argument("--conda-env", default="master-smells")
    arguments.add_argument("--module", default="anaconda")
    arguments.add_argument("--mail-user", default="yakovelm@post.bgu.ac.il")
    arguments.add_argument("--dry-run", action="store_true")
    args = arguments.parse_args()
    if args.cpus < 1 or args.stage not in STAGES[kind]:
        raise ValueError("Invalid CPU count or stage.")
    if args.missing_records is not None and not args.source:
        raise ValueError("A collection approval requires one explicit --source, not an array.")
    root = study(args.storage, args.run_id)
    if args.stage in SOURCE_STAGES and not args.source:
        if args.stage in ("export-windows", "predict"):
            raise ValueError("Select one --source for export or prediction.")
        sources = sorted(verify_study(root)["sources"])
    else:
        sources = [args.source]
    submission_id = identifier(args.run_id) + "-" + args.stage + "-" + uuid.uuid4().hex[:8]
    run_root = REPO / "Tasks" / TASKS[kind] / "cluster_runs" / submission_id
    forwarded = ("storage", "run_id", "candidates", "sources", "prior_manifest", "from_run", "missing_records", "profile",
                 "fixture", "expected", "exclusions", "bundle", "config", "report_output", "input", "output", "family", "variant")
    commands = []
    for source in sources:
        args.source = source
        validate_arguments(args)
        command = ["python", "-u", str(REPO / "Tasks" / TASKS[kind] / "run_task.py"),
                   "--stage", args.stage]
        for name in forwarded:
            value = getattr(args, name)
            if value is not None:
                if isinstance(value, Path):
                    value = value.expanduser().resolve()
                command.extend(["--" + name.replace("_", "-"), str(value)])
        if source:
            command += ["--source", source]
        if args.stage == "report" and args.report_output is None:
            command += ["--report-output", str(run_root / "results/code_smell_report.json")]
        commands.append(command)
    text = render(args, commands, run_root)
    if args.dry_run:
        print(text)
        return
    with lock(Path.home() / ".cache/master-code-smells/submission.lock"):
        active = subprocess.check_output(["squeue", "--me", "--noheader", "--format=%j"], text=True)
        if any(name.strip().startswith("master-smells-") for name in active.splitlines()):
            raise ValueError("Another code-smell array is active; wait before the next stage.")
        run_root.mkdir(parents=True, exist_ok=False)
        (run_root / "logs").mkdir()
        (run_root / "results").mkdir()
        (run_root / "submit.sbatch").write_text(text)
        plan = {"schema": "code-smell-jobs-v1", "run_id": args.run_id, "stage": args.stage,
                "study": str(root), "commands": commands, "sources": sources, "status": "submitting"}
        write_json(run_root / "job_plan.json", plan)
        try:
            job = subprocess.check_output(["sbatch", "--parsable", str(run_root / "submit.sbatch")],
                                          text=True).strip().split(";")[0]
        except subprocess.CalledProcessError:
            write_json(run_root / "job_plan.json", {**plan, "status": "submission_failed"})
            raise
        if not job.isdigit():
            raise ValueError("Unexpected sbatch response; check squeue before retrying.")
        write_json(run_root / "job_plan.json", {**plan, "status": "submitted", "job_id": job})
        (run_root / "submitted_jobs.tsv").write_text(
            "source\tjob_id\tresults\tstdout\tstderr\n" + "".join(
                f"{source or 'all'}\t{job}_{index}\t{root}\t{run_root}/logs/job-{job}_{index}.out\t"
                f"{run_root}/logs/job-{job}_{index}.err\n" for index, source in enumerate(sources)))
        (run_root.parent / "latest_run.txt").write_text(submission_id + "\n")
        print(f"Submitted {job}. Study: {root}. Logs: {run_root / 'logs'}")
