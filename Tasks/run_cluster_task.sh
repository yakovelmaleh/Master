#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./Tasks/run_cluster_task.sh [--pull] <task-name> [task arguments...]
  ./Tasks/run_cluster_task.sh --pull-only
  ./Tasks/run_cluster_task.sh --list

Options:
  --pull       Run "git pull --ff-only" before submitting the task.
  --pull-only  Switch to main, pull changes, and exit without running a task.
  --list       List tasks that provide a cluster submission script.

Example:
  ./Tasks/run_cluster_task.sh --pull jira-url-to-instability-model --refresh
EOF
}

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
pull_first=false
pull_only=false

while (($#)); do
  case "$1" in
    --pull)
      pull_first=true
      shift
      ;;
    --pull-only)
      pull_only=true
      shift
      ;;
    --list)
      for submit_script in "$SCRIPT_DIR"/*/cluster/submit_jobs.sh; do
        [[ -e "$submit_script" ]] || continue
        basename "$(dirname "$(dirname "$submit_script")")"
      done
      exit 0
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    -*)
      echo "Unknown master option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      break
      ;;
  esac
done

if [[ "$pull_only" == true ]]; then
  if (($# != 0)); then
    echo "--pull-only does not accept a task name or task arguments." >&2
    usage >&2
    exit 2
  fi
  git -C "$REPO_ROOT" switch main
  git -C "$REPO_ROOT" pull --ff-only origin main
  echo "Repository updated. No task was run."
  exit 0
fi

if (($# == 0)); then
  usage >&2
  exit 2
fi

task_name=$1
shift

if [[ "$pull_first" == true ]]; then
  git -C "$REPO_ROOT" pull --ff-only
fi

submit_script="$SCRIPT_DIR/$task_name/cluster/submit_jobs.sh"

if [[ ! -f "$submit_script" ]]; then
  echo "Task '$task_name' has no cluster launcher at:" >&2
  echo "  $submit_script" >&2
  echo "Available tasks:" >&2
  "$0" --list >&2
  exit 2
fi

exec bash "$submit_script" "$@"
