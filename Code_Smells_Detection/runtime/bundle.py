"""Allowlisted review metadata; never package fetched source, tools or fitted models."""

import argparse
import json
from pathlib import Path
import shutil


METADATA = {"code_smell_report.json", "job_plan.json", "submitted_jobs.tsv"}
DEFINITION_SUFFIXES = {".py", ".sh", ".ps1", ".md", ".json", ".txt", ".csproj", ".cs", ".java"}
DEFINITION_DIRECTORIES = {"cluster", "tests", "profiles", "windows", "docs", "jira_pipeline", "unstable_model"}
EXCLUDED = {"cluster_runs", "raw", "cache", "tools", "snapshots", "reports", "models",
            "__pycache__", ".pytest_cache", "results", "runs"}


def copy_bundle(source, destination, definition=False):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination or source in destination.parents:
        raise ValueError("Bundle destination must not be inside its source.")
    destination.mkdir(parents=True, exist_ok=True)
    copied = []
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if path.is_symlink():
            continue
        if not path.is_file():
            continue
        if definition:
            allowed = (
                (len(relative.parts) == 1 or relative.parts[0] in DEFINITION_DIRECTORIES)
                and not any(part in EXCLUDED or part.startswith(".") for part in relative.parts)
                and path.name not in METADATA
                and path.suffix in DEFINITION_SUFFIXES
            )
        else:
            allowed = path.name in METADATA
            if path.name == "code_smell_report.json" and json.loads(path.read_text()).get("schema") != "code-smell-report-v1":
                raise ValueError("Unrecognized code-smell report.")
        if not allowed:
            continue
        if path.stat().st_size > 90 * 1024 * 1024:
            raise ValueError(f"Metadata exceeds review size limit: {relative}")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied.append(str(relative))
    return copied


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--definition", action="store_true")
    args = parser.parse_args()
    for path in copy_bundle(args.source, args.destination, args.definition):
        print(path)


if __name__ == "__main__":
    main()
