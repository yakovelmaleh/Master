import argparse
import json
from pathlib import Path

from .orchestrator import run_pipeline


TASK_DIR = Path(__file__).resolve().parents[1]


def build_parser():
    parser = argparse.ArgumentParser(
        allow_abbrev=False,
        description=(
            "Download Jira issues from a repository URL, reproduce the "
            "instability preprocessing, and train a model."
        )
    )
    parser.add_argument("--jira-url", required=True)
    parser.add_argument(
        "--project",
        help=(
            "Optional Jira project key. When omitted, the run includes all "
            "projects in the repository."
        ),
    )
    parser.add_argument(
        "--jql",
        help="Additional/alternative issue condition; defaults to type != Bug.",
    )
    parser.add_argument(
        "--run-name",
        help=(
            "Output folder name. Defaults to <repository> or "
            "<repository>-<project>."
        ),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=TASK_DIR / "runs",
    )
    parser.add_argument(
        "--max-issues",
        type=int,
        help="Bound the download for testing or incremental runs.",
    )
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
        help=(
            "Require statusCategory = Done. Use --no-terminal-only to "
            "include active issues."
        ),
    )
    terminal_group.add_argument(
        "--no-terminal-only",
        dest="terminal_only",
        action="store_false",
        help="Include active issues.",
    )
    parser.set_defaults(terminal_only=True)

    evidence_group = parser.add_mutually_exclusive_group()
    evidence_group.add_argument(
        "--require-pr-evidence",
        dest="require_pr_evidence",
        action="store_true",
        help=(
            "Require a GitHub URL in comments. Use "
            "--no-require-pr-evidence to disable."
        ),
    )
    evidence_group.add_argument(
        "--no-require-pr-evidence",
        dest="require_pr_evidence",
        action="store_false",
        help="Do not require a GitHub URL in comments.",
    )
    parser.set_defaults(require_pr_evidence=True)
    parser.add_argument(
        "--require-current-sprint",
        action="store_true",
        help="Restrict to a populated current Sprint field; excludes history-only sprints.",
    )
    parser.add_argument("--refresh", action="store_true")
    return parser


def main():
    args = build_parser().parse_args()
    result = run_pipeline(args)
    print(json.dumps(result, indent=2, default=str))
