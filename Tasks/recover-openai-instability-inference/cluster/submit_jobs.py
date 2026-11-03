#!/usr/bin/env python3
"""Submit the activated recovery once, with bounded sequential work and ALL mail."""

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

TASK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TASK))

from recovery import CHECKS, REPORT_SCHEMA, REVIEW_SCHEMA, implementation_hash
from run_recovery import exclusive_json, frozen_study
from cloud_control import ControlError, unexpired
from cost_control import check_approval
from protocol import digest, exclusive_lock, external_path, file_hash, read_json, slug, study_id, write_json


def directive(value):
    if not value or any(c.isspace() for c in value) or "#" in value:
        raise ValueError("Invalid SLURM directive.")
    return value


def context(storage, run_id, review_path=None):
    storage = external_path(storage)
    root = storage / "openai-runs" / slug(run_id)
    config = frozen_study(root)
    status = read_json(root / "recovery/status/activate.json")
    if status.get("status") != "succeeded" or status.get("result", {}).get("activated") is not True:
        raise ValueError("A successful recovery activation is required.")
    activation = status["result"]
    expected = activation["review_sha256"]
    if review_path is None:
        matches = []
        for path in (Path.home() / ".local/state/master-openai").glob("recovery-approved*.json"):
            try:
                if digest(read_json(path)) == expected:
                    matches.append(path)
            except json.JSONDecodeError:
                continue
        if len(matches) != 1:
            raise ValueError("No unique matching approved review; supply its exact --review path.")
        review_path = matches[0]
    review_path = external_path(review_path)
    review = read_json(review_path)
    if (digest(review) != expected or review.get("schema") != REVIEW_SCHEMA
            or review.get("run") != study_id(root)
            or review.get("study_sha256") != digest(read_json(root / "study.json"))
            or review.get("prepared_sha256") != file_hash(root / "prepared.json")
            or review.get("seal_sha256") != digest(read_json(root / "sealed.json"))
            or review.get("implementation_sha256") != implementation_hash()
            or any(review.get("checks", {}).get(key) is not True for key in CHECKS)):
        raise ValueError("Review differs from the activated, frozen study.")
    unexpired(review["expires_at"])
    approval = read_json(root / "authorization.json")["approval"]
    check_approval(approval, review["study_sha256"], config)
    if approval["scope"] != "full":
        raise ValueError("Full-study authorization is required.")
    prepared = read_json(root / "prepared.json")
    total = sum(
        (entry["partitions"]["test"]["rows"] + config["batch_rows"] - 1) // config["batch_rows"]
        for entry in prepared["entries"].values()
    )
    batches = activation["remaining_test_batches"]
    if (type(batches) is not int or not 1 <= batches <= total
            or review.get("remaining_test_batches") != batches):
        raise ValueError("Remaining batch count differs from the reviewed activation.")
    return root, review_path, expected, batches


def paths(root, review_hash):
    directory = root / "recovery/jobs" / review_hash
    return directory, directory / "submission.json"


def no_worker_marker(root):
    if any((root / "recovery").glob("*.started")):
        raise ValueError("A recovery worker already started; inspect its job before any resubmission. Keep its marker.")


def render(plan, manifest):
    directory = manifest.parent
    lines = [
        "#!/usr/bin/env bash",
        "#SBATCH --job-name=master-openai-recovery",
        "#SBATCH --partition=" + directive(plan["partition"]),
        "#SBATCH --time=" + directive(plan["time"]),
        "#SBATCH --mem=8G",
        "#SBATCH --ntasks=1",
        "#SBATCH --cpus-per-task=2",
        "#SBATCH --no-requeue",
        "#SBATCH --mail-user=" + directive(plan["mail_user"]),
        "#SBATCH --mail-type=ALL",
        "#SBATCH --output=" + directive(str(directory / "slurm-%j.out")),
        "#SBATCH --error=" + directive(str(directory / "slurm-%j.err")),
        "set -euo pipefail", "umask 077",
        "module load anaconda", "source activate master-openai",
        'export PATH="$PATH:$HOME/.local/share/master-azure-cli/bin"',
        "export AZURE_TOKEN_CREDENTIALS=AzureCliCredential",
        "export PYTHONUNBUFFERED=1",
        shlex.join(["python", "-u", str(Path(__file__).resolve()), "--execute", str(manifest)]),
        "",
    ]
    return "\n".join(lines)


def submit(args):
    root, review, review_hash, batches = context(args.storage, args.run_id, args.review)
    directory, manifest = paths(root, review_hash)
    plan = {
        "schema": "openai-recovery-job-v1", "status": "submission_unconfirmed",
        "storage": str(external_path(args.storage)), "run_id": args.run_id,
        "review": str(review), "review_sha256": review_hash, "batches": batches,
        "launcher_sha256": file_hash(Path(__file__)),
        "partition": args.partition, "time": args.time, "mail_user": args.mail_user,
    }
    script = render(plan, manifest)
    if args.dry_run:
        print(script)
        return None
    with exclusive_lock(Path.home() / ".local/state/master-openai/.submission.lock"):
        no_worker_marker(root)
        if manifest.exists():
            raise ValueError("A submission is already recorded; inspect it rather than submitting again.")
        names = subprocess.check_output(
            ["squeue", "--me", "--noheader", "--format=%j"], text=True
        )
        if any(name.startswith("master-openai-") for name in names.splitlines()):
            raise ValueError("A Master OpenAI job is already active.")
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / "submit.sbatch").open("x") as stream:
            stream.write(script)
        plan["script_sha256"] = file_hash(directory / "submit.sbatch")
        # Persist intent before sbatch; a lost response must not trigger resubmission.
        exclusive_json(manifest, plan)
        result = subprocess.check_output(
            ["sbatch", "--parsable", str(directory / "submit.sbatch")], text=True
        ).strip().split(";")[0]
        if not result.isdigit():
            raise ValueError("Submission response is ambiguous; inspect the queue and saved submission.")
        write_json(manifest, {**plan, "status": "submitted", "job_id": result})
    print(f"Submitted recovery job {result}; {batches} test batches then report.")
    print(f"Email: {args.mail_user} (ALL). Logs: {directory}")
    return result


def run_job(manifest):
    manifest = external_path(manifest)
    plan = read_json(manifest)
    root, review, review_hash, batches = context(plan["storage"], plan["run_id"], plan["review"])
    _, expected_manifest = paths(root, review_hash)
    if (manifest != expected_manifest or plan.get("schema") != "openai-recovery-job-v1"
            or plan.get("status") not in ("submission_unconfirmed", "submitted")
            or plan["review_sha256"] != review_hash or plan["batches"] != batches
            or plan["launcher_sha256"] != file_hash(Path(__file__))
            or plan["script_sha256"] != file_hash(manifest.parent / "submit.sbatch")):
        raise ValueError("Submission evidence or launcher changed.")
    job_id = os.environ.get("SLURM_JOB_ID", "")
    if not job_id.isdigit() or (plan.get("job_id") and plan["job_id"] != job_id):
        raise ValueError("The scheduled job identity differs from its submission.")
    with exclusive_lock(Path.home() / ".local/state/master-openai/.submission.lock"):
        no_worker_marker(root)
        exclusive_json(root / "recovery" / f"launcher-{review_hash}.started",
                       {"job_id": job_id, "review_sha256": review_hash})
    worker_status = manifest.parent / "worker-status.json"
    write_json(worker_status, {"status": "running", "job_id": job_id, "completed_test_batches": 0})
    command = [
        sys.executable, "-u", str(TASK / "run_recovery.py"),
    ]
    args = ["--storage", plan["storage"], "--run-id", plan["run_id"], "--review", str(review)]
    completed = 0
    try:
        for _ in range(batches):
            subprocess.run([*command, "test", *args], check=True)
            status = read_json(root / "recovery/status/test.json")
            if status["status"] != "succeeded" or status["result"].get("scope_complete"):
                raise ValueError("Unexpected test progress; stop without extra invocations.")
            completed += 1
            write_json(worker_status, {
                "status": "running", "job_id": job_id, "completed_test_batches": completed,
            })
        subprocess.run([*command, "report", *args], check=True)
        report = read_json(root / "recovery/llm_report.json")
        if (report["schema"] != REPORT_SCHEMA or report["complete"] is not True
                or len(report["cells"]) != 8
                or report["execution_recovery"]["review_sha256"] != review_hash):
            raise ValueError("The annotated report is incomplete or belongs to another review.")
        write_json(worker_status, {"status": "succeeded", "job_id": job_id,
                                   "completed_test_batches": completed, "passed": report["passed"]})
        print("FULL_STUDY_COMPLETE", "performance_gates_passed=", report["passed"])
    except Exception as error:
        write_json(worker_status, {"status": "failed", "job_id": job_id,
                                   "completed_test_batches": completed, "error_type": type(error).__name__})
        raise


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage", default=str(Path.home() / "master-openai"))
    parser.add_argument("--run-id", default="openai-prompt-01")
    parser.add_argument("--review", type=Path)
    parser.add_argument("--partition", default="main")
    parser.add_argument("--time", default="2-00:00:00")
    parser.add_argument("--mail-user", default="yakovelm@post.bgu.ac.il")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.execute:
        run_job(args.execute)
    else:
        submit(args)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        detail = str(error) if isinstance(error, (ControlError, ValueError, FileNotFoundError)) else type(error).__name__
        print("LAUNCHER STOPPED: " + detail + "; inspect saved evidence before retrying.", file=sys.stderr)
        raise SystemExit(1) from None
