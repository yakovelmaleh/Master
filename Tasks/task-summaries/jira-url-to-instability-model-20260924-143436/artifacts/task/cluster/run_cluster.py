#!/usr/bin/env python3

import argparse
import json
import sys
from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path


TASK_DIR = Path(__file__).resolve().parents[1]
MASTER_DIR = TASK_DIR.parents[1]
sys.path.insert(0, str(TASK_DIR))

from jira_pipeline.orchestrator import run_pipeline


DEFAULT_SOURCES_FILE = (
    MASTER_DIR / "Source" / "jira_data_for_instability_cluster.json"
)


def load_sources(path, selected_names=None):
    with Path(path).open(encoding="utf-8") as source_file:
        payload = json.load(source_file)
    if not isinstance(payload, dict):
        raise ValueError("The sources file must contain a JSON object.")

    selected = {
        value.casefold() for value in selected_names or []
    }
    sources = []
    for name, value in payload.items():
        if selected and name.casefold() not in selected:
            continue
        entry = {"jira_url": value} if isinstance(value, str) else dict(value)
        if entry.get("enabled", True) is False:
            continue
        jira_url = entry.get("jira_url")
        if not jira_url:
            raise ValueError(f"Source {name!r} has no jira_url.")
        sources.append(
            {
                "name": name,
                "jira_url": jira_url,
                "project": entry.get("project"),
                "run_name": entry.get("run_name"),
                "jql": entry.get("jql"),
                "require_pr_evidence": entry.get(
                    "require_pr_evidence"
                ),
            }
        )

    if selected:
        found = {source["name"].casefold() for source in sources}
        missing = sorted(selected - found)
        if missing:
            raise ValueError(
                "Requested sources were not found or were disabled: "
                + ", ".join(missing)
            )
    if not sources:
        raise ValueError("No enabled Jira sources were selected.")
    return sources


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Run the Jira URL to instability model pipeline for every "
            "repository in a cluster sources JSON file."
        )
    )
    parser.add_argument(
        "--sources-file",
        type=Path,
        default=DEFAULT_SOURCES_FILE,
    )
    parser.add_argument(
        "--only",
        nargs="+",
        help="Run only the named source entries, for example Apache Qt.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=TASK_DIR / "runs",
    )
    parser.add_argument(
        "--jql",
        help="Shared issue condition; defaults to type != Bug.",
    )
    parser.add_argument("--max-issues", type=int)
    parser.add_argument(
        "--label-threshold",
        type=int,
        choices=[5, 10, 15, 20],
        default=5,
    )
    terminal_group = parser.add_mutually_exclusive_group()
    terminal_group.add_argument(
        "--terminal-only",
        dest="terminal_only",
        action="store_true",
    )
    terminal_group.add_argument(
        "--no-terminal-only",
        dest="terminal_only",
        action="store_false",
    )
    parser.set_defaults(terminal_only=True)

    evidence_group = parser.add_mutually_exclusive_group()
    evidence_group.add_argument(
        "--require-pr-evidence",
        dest="require_pr_evidence",
        action="store_true",
    )
    evidence_group.add_argument(
        "--no-require-pr-evidence",
        dest="require_pr_evidence",
        action="store_false",
    )
    parser.set_defaults(require_pr_evidence=True)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on the first repository failure.",
    )
    return parser


def run_cluster(args):
    sources = load_sources(args.sources_file, args.only)
    args.output_root.mkdir(parents=True, exist_ok=True)
    results = []

    for index, source in enumerate(sources, start=1):
        print(
            f"[{index}/{len(sources)}] Starting {source['name']}: "
            f"{source['jira_url']}",
            flush=True,
        )
        pipeline_args = Namespace(
            jira_url=source["jira_url"],
            project=source["project"],
            jql=source["jql"] or args.jql,
            run_name=source["run_name"],
            output_root=args.output_root,
            max_issues=args.max_issues,
            label_threshold=args.label_threshold,
            terminal_only=args.terminal_only,
            require_pr_evidence=(
                args.require_pr_evidence
                if source["require_pr_evidence"] is None
                else source["require_pr_evidence"]
            ),
            refresh=args.refresh,
        )
        try:
            output = run_pipeline(pipeline_args)
            results.append(
                {
                    "source": source["name"],
                    "status": "succeeded",
                    **output,
                }
            )
            print(f"Finished {source['name']}", flush=True)
        except Exception as error:
            results.append(
                {
                    "source": source["name"],
                    "jira_url": source["jira_url"],
                    "status": "failed",
                    "error": str(error),
                }
            )
            print(
                f"Failed {source['name']}: {error}",
                file=sys.stderr,
                flush=True,
            )
            if args.fail_fast:
                break

    summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "sources_file": str(args.sources_file.resolve()),
        "output_root": str(args.output_root.resolve()),
        "settings": {
            "max_issues": args.max_issues,
            "label_threshold": args.label_threshold,
            "terminal_only": args.terminal_only,
            "require_pr_evidence": args.require_pr_evidence,
            "refresh": args.refresh,
        },
        "succeeded": sum(item["status"] == "succeeded" for item in results),
        "failed": sum(item["status"] == "failed" for item in results),
        "results": results,
    }
    summary_path = args.output_root / "cluster_run_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(f"Cluster summary: {summary_path.resolve()}")
    return summary


def main():
    args = build_parser().parse_args()
    summary = run_cluster(args)
    if summary["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
