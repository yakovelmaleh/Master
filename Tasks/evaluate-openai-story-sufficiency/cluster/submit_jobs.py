#!/usr/bin/env python3
"""Submit one offline sufficiency preparation job; never launch Azure stages."""

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

TASK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TASK))

from sufficiency import root_at, signature
from protocol import digest, exclusive_lock, external_path, file_hash, read_json, slug, write_json


def directive(value):
    if not value or any(c.isspace() for c in value) or "#" in value:
        raise ValueError("Invalid SLURM directive.")
    return value


def exclusive_json(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())


def render(args, manifest):
    directory = manifest.parent
    return "\n".join([
        "#!/usr/bin/env bash",
        "#SBATCH --job-name=master-openai-sufficiency-prepare",
        "#SBATCH --partition=" + directive(args.partition),
        "#SBATCH --time=" + directive(args.time),
        "#SBATCH --mem=8G",
        "#SBATCH --ntasks=1",
        "#SBATCH --cpus-per-task=2",
        "#SBATCH --no-requeue",
        "#SBATCH --mail-user=" + directive(args.mail_user),
        "#SBATCH --mail-type=ALL",
        "#SBATCH --output=" + directive(str(directory / "slurm-%j.out")),
        "#SBATCH --error=" + directive(str(directory / "slurm-%j.err")),
        "set -euo pipefail", "umask 077",
        "module load anaconda", "source activate master-openai",
        "export PYTHONUNBUFFERED=1",
        shlex.join(["python", "-u", str(Path(__file__).resolve()), "--execute", str(manifest)]),
        "",
    ])


def submit(args):
    storage = external_path(args.storage)
    run_id = slug(args.run_id)
    root = root_at(storage, run_id)
    source = external_path(args.source_run or storage / "openai-runs/openai-prompt-01")
    current = signature(source)
    if (root / "study.json").exists() and read_json(root / "study.json") != current:
        raise ValueError("Keep the existing run; select a new --run-id.")
    directory = root / "jobs/prepare"
    manifest = directory / "submission.json"
    script = render(args, manifest)
    if args.dry_run:
        print(script)
        return
    with exclusive_lock(Path.home() / ".local/state/master-openai/.submission.lock"):
        if manifest.exists() or (directory / "worker.started").exists():
            raise ValueError("Submission already recorded; inspect its job and evidence before retrying.")
        names = subprocess.check_output(
            ["squeue", "--me", "--noheader", "--format=%j"], text=True
        )
        if any(name.startswith("master-openai-") for name in names.splitlines()):
            raise ValueError("A Master OpenAI job is already active.")
        directory.mkdir(parents=True, exist_ok=True)
        script_path = directory / "submit.sbatch"
        with script_path.open("x") as stream:
            stream.write(script)
        plan = {
            "schema": "openai-sufficiency-prepare-job-v1",
            "status": "submission_unconfirmed", "cloud_access": False,
            "storage": str(storage), "run_id": run_id, "source": str(source),
            "study_sha256": digest(current), "launcher_sha256": file_hash(Path(__file__)),
            "script_sha256": file_hash(script_path),
        }
        # A lost sbatch response must not trigger another submission.
        exclusive_json(manifest, plan)
        job_id = subprocess.check_output(
            ["sbatch", "--parsable", str(script_path)], text=True
        ).strip().split(";")[0]
        if not job_id.isdigit():
            raise ValueError("Submission unconfirmed; inspect the queue and saved evidence.")
        write_json(manifest, {**plan, "status": "submitted", "job_id": job_id})
    print(f"Submitted offline preparation job {job_id}. Logs and status: {directory}")
    return job_id


def run_job(manifest):
    manifest = external_path(manifest)
    plan = read_json(manifest)
    root = root_at(plan["storage"], plan["run_id"])
    directory = root / "jobs/prepare"
    if (manifest != directory / "submission.json"
            or plan.get("schema") != "openai-sufficiency-prepare-job-v1"
            or plan.get("status") not in ("submission_unconfirmed", "submitted")
            or plan.get("cloud_access") is not False
            or plan["launcher_sha256"] != file_hash(Path(__file__))
            or plan["script_sha256"] != file_hash(directory / "submit.sbatch")
            or plan["study_sha256"] != digest(signature(plan["source"]))):
        raise ValueError("Submission or source provenance changed; keep evidence and stop.")
    job_id = os.environ.get("SLURM_JOB_ID", "")
    if not job_id.isdigit() or (plan.get("job_id") and plan["job_id"] != job_id):
        raise ValueError("Scheduled job identity differs from submission.")
    with exclusive_lock(Path.home() / ".local/state/master-openai/.submission.lock"):
        exclusive_json(directory / "worker.started", {"job_id": job_id})
    status_path = directory / "worker-status.json"
    status = {"status": "running", "job_id": job_id, "cloud_access": False}
    write_json(status_path, status)
    try:
        subprocess.run([
            sys.executable, "-u", str(TASK / "run_experiment.py"), "prepare",
            "--storage", plan["storage"], "--run-id", plan["run_id"],
            "--source-run", plan["source"],
        ], check=True)
        if (digest(read_json(root / "study.json")) != plan["study_sha256"]
                or not (root / "prepared.json").is_file()
                or not (root / "approval.template.json").is_file()):
            raise ValueError("Preparation did not produce the expected study and approval template.")
        write_json(status_path, {**status, "status": "succeeded", "prepared": True})
        print("OFFLINE_PREPARATION_COMPLETE; Azure execution still requires separate approvals.")
    except Exception as error:
        write_json(status_path, {**status, "status": "failed", "error_type": type(error).__name__})
        raise


def main(argv=None):
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("prepare",), default="prepare")
    parser.add_argument("--storage", default=str(Path.home() / "master-openai"))
    parser.add_argument("--run-id", default="openai-sufficiency-03")
    parser.add_argument("--source-run", type=Path)
    parser.add_argument("--partition", default="main")
    parser.add_argument("--time", default="04:00:00")
    parser.add_argument("--mail-user", default="yakovelm@post.bgu.ac.il")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.execute:
        run_job(args.execute)
    else:
        submit(args)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        detail = str(error) if isinstance(error, (ValueError, FileNotFoundError)) else type(error).__name__
        print("LAUNCHER STOPPED: " + detail + "; keep saved evidence.", file=sys.stderr)
        raise SystemExit(1) from None
