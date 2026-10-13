"""Stage CLI used by task-owned SLURM wrappers."""

import argparse
from pathlib import Path

from .common import REPO, TASKS, digest, stage_state, study, verify_study


STAGES = {
    "prepare": ("environment", "audit", "enrich", "freeze", "fetch-code"),
    "detect": ("setup", "qualify", "detect", "export-windows", "import-windows", "labels"),
    "train": ("validate", "train", "seal", "test", "report", "predict"),
}
SOURCE_STAGES = {"enrich", "freeze", "fetch-code", "detect", "export-windows", "train", "test", "predict"}


def parser(kind=None):
    result = argparse.ArgumentParser(description=__doc__)
    if kind is None:
        result.add_argument("kind", choices=TASKS)
    else:
        result.set_defaults(kind=kind)
    result.add_argument("--stage", required=True)
    result.add_argument("--storage", type=Path, required=True)
    result.add_argument("--run-id", required=True)
    result.add_argument("--source")
    result.add_argument("--candidates", type=Path)
    result.add_argument("--sources", type=Path)
    result.add_argument("--prior-manifest", type=Path)
    result.add_argument("--profile", type=Path)
    result.add_argument("--fixture", type=Path)
    result.add_argument("--expected", type=Path)
    result.add_argument("--exclusions", type=Path)
    result.add_argument("--bundle", type=Path)
    result.add_argument("--config", type=Path)
    result.add_argument("--report-output", type=Path)
    result.add_argument("--input", type=Path)
    result.add_argument("--output", type=Path)
    result.add_argument("--family", choices=("RF", "XGboost", "NN"))
    result.add_argument("--variant", choices=("baseline", "refactored"))
    return result


def validate_arguments(args):
    if args.stage not in STAGES[args.kind]:
        raise ValueError(f"Unsupported stage for {args.kind}: {args.stage}")
    required = {
        "audit": ("candidates", "sources"), "setup": ("profile",),
        "qualify": ("profile", "fixture", "expected"), "detect": ("profile",),
        "export-windows": ("profile", "bundle"), "import-windows": ("bundle",),
        "predict": ("input", "output", "family", "variant"),
    }.get(args.stage, ())
    for name in required:
        if getattr(args, name) is None:
            raise ValueError(f"--{name.replace('_', '-')} is required for {args.stage}.")
    if args.stage in SOURCE_STAGES and not args.source:
        raise ValueError("--source is required for source-level execution.")


def main(kind=None):
    args = parser(kind).parse_args()
    validate_arguments(args)
    root = study(args.storage, args.run_id)
    if args.stage not in ("environment", "audit", "setup", "qualify"):
        verify_study(root)
    unit = args.source or "all"
    if args.stage in ("setup", "qualify", "detect"):
        from .detectors import load_profile
        unit += "-" + load_profile(args.profile)["language"]
    fingerprint = digest({key: str(value) for key, value in vars(args).items()})
    with stage_state(root, args.stage, unit, fingerprint):
        dispatch(args, root)


def dispatch(args, root):
    if args.kind == "prepare":
        if args.stage == "environment":
            import json
            import subprocess
            environments = json.loads(subprocess.check_output(["conda", "env", "list", "--json"], text=True))
            if not any(Path(path).name == "master-smells" for path in environments["envs"]):
                subprocess.run(["conda", "create", "--yes", "-n", "master-smells", "python=3.11"], check=True)
            subprocess.run(["conda", "run", "--no-capture-output", "-n", "master-smells",
                            "python", "-m", "pip", "install", "-r",
                            str(REPO / "Tasks/train-code-smell-models/requirements.txt")], check=True)
            subprocess.run(["conda", "run", "--no-capture-output", "-n", "master-smells",
                            "python", "-m", "pip", "check"], check=True)
            return
        from .prepare import audit, enrich, freeze
        from .evidence import fetch_code
        if args.stage == "audit":
            audit(root, args.candidates, args.sources, args.prior_manifest)
        elif args.stage == "enrich":
            enrich(root, args.source)
        elif args.stage == "freeze":
            freeze(root, args.source)
        else:
            fetch_code(root, args.storage, args.source)
    elif args.kind == "detect":
        from .detectors import install_profile, qualify, detect, labels
        from .windows import export_work, import_work
        if args.stage == "setup":
            install_profile(args.storage, args.profile)
        elif args.stage == "qualify":
            qualify(args.storage, args.profile, args.fixture, args.expected)
        elif args.stage == "detect":
            detect(root, args.storage, args.source, args.profile)
        elif args.stage == "export-windows":
            export_work(root, args.source, args.profile, args.bundle)
        elif args.stage == "import-windows":
            import_work(root, args.bundle)
        else:
            labels(root, args.exclusions)
    else:
        from . import models
        if args.stage == "validate":
            models.validate(root, args.config)
        elif args.stage == "train":
            models.train(root, args.source)
        elif args.stage == "seal":
            models.seal(root)
        elif args.stage == "test":
            models.test(root, args.source)
        elif args.stage == "report":
            models.report(root, args.report_output)
        else:
            models.infer(root, args.source, args.family, args.variant, args.input, args.output)


if __name__ == "__main__":
    main()
