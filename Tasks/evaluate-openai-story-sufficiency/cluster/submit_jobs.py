#!/usr/bin/env python3
"""Submit one offline preparation or explicitly approved, bounded cloud-stage job."""

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

TASK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TASK))

from sufficiency import check_approval, root_at, signature
from protocol import digest, exclusive_lock, external_path, file_hash, read_json, slug, write_json
from cost_control import CONTROL, money
from renew_storage import binding_at, validate as validate_storage

FAILURE_TASK = TASK.parent / "recover-openai-sufficiency-smoke"
sys.path.insert(0, str(FAILURE_TASK))
from inspect_failure import queued_review as failure_review
from one_shot import queued_review as diagnostic_review

MODEL_STAGES = ("preflight", "smoke", "validate", "seal", "test", "report")
INSPECTION_STAGES = ("inspect-storage", "inspect-failure")
STAGES = ("prepare", *INSPECTION_STAGES, *MODEL_STAGES, "diagnose-smoke")


def directive(value):
    if not value or any(c.isspace() for c in value) or "#" in value:
        raise ValueError("Invalid SLURM directive.")
    return value


def exclusive_json(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())


def job_directory(root, stage, label=None):
    return root / "jobs" / (stage if label is None else stage + "-" + slug(label))


def model_review(root, stage, approval_path, study):
    if read_json(root / "study.json") != study:
        raise ValueError("Prepared study differs from current source.")
    path = external_path(approval_path) if stage == "preflight" else root / "authorization.json"
    value = read_json(path)
    approval = value if stage == "preflight" else value["approval"]
    check_approval(approval, digest(study), study["config"])
    storage_path = CONTROL / "cloud-approval.json"
    storage = read_json(storage_path)
    validate_storage(storage, binding_at(), root)
    if (approval["authority_sha256"] != storage["authority_sha256"]
            or money(approval["storage_reserve_usd"]) != money(storage["storage"]["reserve_usd"])):
        raise ValueError("Model and storage approvals differ.")
    if stage in ("seal", "test") and approval["scope"] != "full":
        raise ValueError("Sealing and final test require separate full-study approval.")
    return {
        "approval_path": str(path), "approval_sha256": file_hash(path),
        "storage_approval_sha256": file_hash(storage_path),
        "prepared_sha256": file_hash(root / "prepared.json"),
    }


def render(args, manifest):
    directory = manifest.parent
    return "\n".join([
        "#!/usr/bin/env bash",
        "#SBATCH --job-name=master-openai-sufficiency-" + args.stage,
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
        *(['export PATH="$PATH:$HOME/.local/share/master-azure-cli/bin"',
           "export AZURE_TOKEN_CREDENTIALS=AzureCliCredential"] if args.stage != "prepare" else []),
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
    if args.stage != "prepare" and not (root / "prepared.json").is_file():
        raise ValueError("Complete offline preparation before requesting a cloud stage.")
    review = model_review(root, args.stage, args.approval, current) if args.stage in MODEL_STAGES else None
    failure = failure_review(root, external_path(args.failure)) if args.stage == "inspect-failure" else None
    diagnostic = diagnostic_review(root, external_path(args.review)) if args.stage == "diagnose-smoke" else None
    directory = job_directory(root, args.stage, args.job_label)
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
            "schema": "openai-sufficiency-cluster-job-v1",
            "status": "submission_unconfirmed", "cloud_access": args.stage != "prepare",
            "stage": args.stage, "inspection_approved": args.execute_approved_inspection,
            "model_stage_approved": args.execute_approved_stage, "job_label": args.job_label,
            "diagnostic_approved": args.execute_approved_diagnostic,
            "storage": str(storage), "run_id": run_id, "source": str(source),
            "study_sha256": digest(current), "launcher_sha256": file_hash(Path(__file__)),
            "script_sha256": file_hash(script_path),
        }
        if args.stage == "inspect-storage":
            plan["inspection_sha256"] = file_hash(TASK / "cluster/inspect_storage.py")
        if review is not None:
            plan["model_review"] = review
        if failure is not None:
            plan["failure_review"] = failure
        if diagnostic is not None:
            plan["diagnostic_review"] = diagnostic
        # A lost sbatch response must not trigger another submission.
        exclusive_json(manifest, plan)
        job_id = subprocess.check_output(
            ["sbatch", "--parsable", str(script_path)], text=True
        ).strip().split(";")[0]
        if not job_id.isdigit():
            raise ValueError("Submission unconfirmed; inspect the queue and saved evidence.")
        write_json(manifest, {**plan, "status": "submitted", "job_id": job_id})
    print(f"Submitted {args.stage} job {job_id}. Logs and status: {directory}")
    return job_id


def run_job(manifest):
    manifest = external_path(manifest)
    plan = read_json(manifest)
    root = root_at(plan["storage"], plan["run_id"])
    stage = plan.get("stage", "prepare")
    if stage not in STAGES or (stage in INSPECTION_STAGES and plan.get("inspection_approved") is not True):
        raise ValueError("Unknown stage or missing explicit inspection approval.")
    if stage in MODEL_STAGES and plan.get("model_stage_approved") is not True:
        raise ValueError("Missing explicit model-stage approval.")
    if stage == "diagnose-smoke" and plan.get("diagnostic_approved") is not True:
        raise ValueError("Missing separate one-shot diagnostic approval.")
    if stage not in (*MODEL_STAGES, "inspect-failure") and plan.get("job_label") is not None:
        raise ValueError("Job labels require a reviewed model stage or failure inspection.")
    directory = job_directory(root, stage, plan.get("job_label"))
    if (manifest != directory / "submission.json"
            or plan.get("schema") != "openai-sufficiency-cluster-job-v1"
            or plan.get("status") not in ("submission_unconfirmed", "submitted")
            or plan.get("cloud_access") is not (stage != "prepare")
            or plan["launcher_sha256"] != file_hash(Path(__file__))
            or plan["script_sha256"] != file_hash(directory / "submit.sbatch")
            or plan["study_sha256"] != digest(signature(plan["source"]))):
        raise ValueError("Submission or source provenance changed; keep evidence and stop.")
    if stage == "inspect-storage" and plan.get("inspection_sha256") != file_hash(TASK / "cluster/inspect_storage.py"):
        raise ValueError("Storage inspection implementation changed after submission.")
    if stage == "inspect-failure":
        review = plan["failure_review"]
        if failure_review(root, external_path(review["failure_path"])) != review:
            raise ValueError("Queued failure evidence, approvals or inspection implementation changed.")
    if stage == "diagnose-smoke":
        review = plan["diagnostic_review"]
        if diagnostic_review(root, external_path(review["review_path"])) != review:
            raise ValueError("Queued one-shot diagnostic review or implementation changed.")
    if stage in MODEL_STAGES:
        review = plan["model_review"]
        if model_review(root, stage, review["approval_path"], signature(plan["source"])) != review:
            raise ValueError("Queued model/storage approval or prepared manifest changed.")
    job_id = os.environ.get("SLURM_JOB_ID", "")
    if not job_id.isdigit() or (plan.get("job_id") and plan["job_id"] != job_id):
        raise ValueError("Scheduled job identity differs from submission.")
    with exclusive_lock(Path.home() / ".local/state/master-openai/.submission.lock"):
        exclusive_json(directory / "worker.started", {"job_id": job_id})
    status_path = directory / "worker-status.json"
    status = {"status": "running", "job_id": job_id, "cloud_access": stage != "prepare"}
    write_json(status_path, status)
    try:
        if stage == "diagnose-smoke":
            subprocess.run([
                sys.executable, "-u", str(FAILURE_TASK / "one_shot.py"), "diagnose",
                "--root", str(root), "--review", plan["diagnostic_review"]["review_path"],
                "--execute-approved-diagnostic",
            ], check=True)
            result = read_json(directory / "diagnostic.json")
            if (result.get("schema") != "sufficiency-one-shot-diagnostic-v1"
                    or result.get("pending_retained") is not True
                    or result.get("completes_smoke") is not False
                    or result.get("authorizes_continuation") is not False
                    or result.get("captured", {}).get("attempt") != 2
                    or result.get("model_requests") not in (0, 1)
                    or not 0 <= result["storage_requests_used"] <= 100):
                raise ValueError("Diagnostic did not produce bounded one-shot evidence.")
            write_json(status_path, {**status, "status": "succeeded", "diagnostic_recorded": True,
                                    "scorable_response": result["scorable_response"],
                                    "pending_retained": True, "completes_smoke": False})
            print("DIAGNOSTIC_RECORDED; pending retained, no continuation authorized.")
            return
        if stage == "inspect-failure":
            command = [
                sys.executable, "-u", str(FAILURE_TASK / "inspect_failure.py"),
                "--root", str(root), "--failure", plan["failure_review"]["failure_path"],
                "--execute-approved-inspection",
            ]
            if plan.get("job_label") is not None:
                command += ["--job-label", plan["job_label"]]
            subprocess.run(command, check=True)
            result = read_json(directory / "inspection.json")
            if (result.get("schema") != "sufficiency-failure-inspection-v1"
                    or result.get("authorizes_inference") is not False
                    or result.get("model_calls") != 0
                    or result.get("inspection_request_limit") != 100
                    or not 0 <= result["inspection_requests_used"] <= 100):
                raise ValueError("Failure inspection did not produce bounded storage-only evidence.")
            write_json(status_path, {**status, "status": "succeeded", "inspected": True})
            print("FAILURE_INSPECTION_COMPLETE; pending state retained, no inference authorized.")
            return
        if stage == "inspect-storage":
            output = directory / "inspection.json"
            subprocess.run([
                sys.executable, "-u", str(TASK / "cluster/inspect_storage.py"),
                "--root", str(root), "--output", str(output), "--execute-approved-inspection",
            ], check=True)
            result = read_json(output)
            if (result.get("schema") != "sufficiency-storage-inspection-v1"
                    or result.get("authorizes_inference") is not False
                    or result.get("model_calls") != 0
                    or result.get("inspection_request_limit") != 100
                    or not 0 <= result["inspection_requests_used"] <= 100):
                raise ValueError("Inspection did not produce the expected bounded storage-only result.")
            write_json(status_path, {**status, "status": "succeeded", "inspected": True})
            print("STORAGE_INSPECTION_COMPLETE; no inference authorized.")
            return
        if stage in MODEL_STAGES:
            command = [
                sys.executable, "-u", str(TASK / "run_experiment.py"), stage,
                "--storage", plan["storage"], "--run-id", plan["run_id"], "--execute-approved-stage",
            ]
            if stage == "preflight":
                command += ["--approval", plan["model_review"]["approval_path"]]
            subprocess.run(command, check=True)
            result = read_json(root / "status" / f"{stage}.json")
            if result.get("status") != "succeeded" or not isinstance(result.get("result"), dict):
                raise ValueError("Model stage did not produce successful status evidence.")
            write_json(directory / "result.json", result)
            write_json(status_path, {**status, "status": "succeeded", "stage": stage, "result": result["result"]})
            print(f"APPROVED_STAGE_COMPLETE: {stage}; no subsequent stage submitted.")
            return
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
    parser.add_argument("--stage", choices=STAGES, default="prepare")
    parser.add_argument("--storage", default=str(Path.home() / "master-openai"))
    parser.add_argument("--run-id", default="openai-sufficiency-04")
    parser.add_argument("--source-run", type=Path)
    parser.add_argument("--partition", default="main")
    parser.add_argument("--time", default="04:00:00")
    parser.add_argument("--mail-user", default="yakovelm@post.bgu.ac.il")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute-approved-inspection", action="store_true")
    parser.add_argument("--failure", type=Path, help="Saved failure evidence, for inspect-failure only.")
    parser.add_argument("--execute-approved-stage", action="store_true")
    parser.add_argument("--execute-approved-diagnostic", action="store_true")
    parser.add_argument("--review", type=Path, help="Separate private one-shot diagnostic review.")
    parser.add_argument("--approval", type=Path, help="Private model approval, for preflight only.")
    parser.add_argument("--job-label", help="Unique label for a separately reviewed model-stage invocation.")
    parser.add_argument("--execute", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.execute:
        run_job(args.execute)
    else:
        if args.stage == "diagnose-smoke":
            if not args.review or (not args.execute_approved_diagnostic and not args.dry_run):
                parser.error("Diagnostic requires --review and separate --execute-approved-diagnostic.")
        elif args.review or args.execute_approved_diagnostic:
            parser.error("One-shot review/consent is only for diagnose-smoke.")
        if (args.stage == "inspect-failure") != (args.failure is not None):
            parser.error("Supply --failure for inspect-failure only.")
        if args.stage in MODEL_STAGES:
            if not args.execute_approved_stage and not args.dry_run:
                parser.error("Model stages need explicit --execute-approved-stage.")
            if (args.stage == "preflight") != (args.approval is not None):
                parser.error("Supply --approval for preflight only.")
        elif args.execute_approved_stage or args.approval or (
            args.job_label is not None and args.stage != "inspect-failure"
        ):
            parser.error("Model-stage flags cannot be used for preparation or storage inspection.")
        if args.stage in INSPECTION_STAGES and not args.execute_approved_inspection and not args.dry_run:
            parser.error("Storage inspection needs explicit --execute-approved-inspection.")
        if args.stage not in INSPECTION_STAGES and args.execute_approved_inspection:
            parser.error("Only storage inspection can use storage-inspection approval.")
        submit(args)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        detail = str(error) if isinstance(error, (ValueError, FileNotFoundError)) else type(error).__name__
        print("LAUNCHER STOPPED: " + detail + "; keep saved evidence.", file=sys.stderr)
        raise SystemExit(1) from None
