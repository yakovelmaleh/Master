#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Create a GitHub PR containing a complete summary bundle for one task.

Usage:
  ./create_task_summary_pr.sh \
    --task TASK_NAME \
    [--run-id RUN_ID | --no-run] \
    [--include PATH]... \
    [--summary TEXT] \
    [--title PR_TITLE] \
    [--dry-run]

Required:
  --task NAME       Task folder under Master/Tasks.

Optional:
  --run-id ID       Include this task cluster run.
  --no-run          Do not include a cluster run.
  --include PATH    Include another repository file or directory. Repeatable.
  --summary TEXT    Add a short human-written summary to the generated README.
  --title TEXT      PR title; defaults to "Summarize task: <task>".
  --dry-run         Build and validate the bundle without Git changes.
  -h, --help        Show this help.

When neither --run-id nor --no-run is supplied, the script includes the run
referenced by cluster_runs/latest_run.txt when that pointer exists.
EOF
}

slug() {
  printf '%s' "$1" |
    tr '[:upper:]' '[:lower:]' |
    sed -E 's/[^a-z0-9._-]+/-/g; s/^-+//; s/-+$//'
}

canonical_directory() {
  (
    cd "$1"
    pwd -P
  )
}

canonical_file() {
  directory=$(dirname "$1")
  filename=$(basename "$1")
  printf '%s/%s\n' "$(canonical_directory "$directory")" "$filename"
}

require_value() {
  option_name=$1
  remaining_count=$2
  if ((remaining_count < 2)); then
    echo "$option_name requires a value." >&2
    exit 2
  fi
}

assert_inside_repo() {
  selected_path=$1
  case "$selected_path" in
    "$REPO_ROOT"|"$REPO_ROOT"/*) ;;
    *)
      echo "Selected path is outside the Master repository: $selected_path" >&2
      exit 2
      ;;
  esac
}

copy_file() {
  source_file=$1
  destination_file=$2
  mkdir -p "$(dirname "$destination_file")"
  cp -pL "$source_file" "$destination_file"
}

copy_tree() {
  source_root=$1
  destination_root=$2
  while IFS= read -r -d '' source_file; do
    relative_path=${source_file#"$source_root"/}
    copy_file "$source_file" "$destination_root/$relative_path"
  done < <(find -L "$source_root" -type f -print0)
}

copy_task_definition() {
  destination_root=$1

  while IFS= read -r -d '' source_file; do
    relative_path=${source_file#"$task_dir"/}
    copy_file "$source_file" "$destination_root/$relative_path"
  done < <(
    find -L "$task_dir" \
      \( -path "$task_dir/cluster_runs" -o -path "$task_dir/runs" \) \
      -prune -o \
      -type f \
      ! -name '.DS_Store' \
      ! -name '*.pyc' \
      ! -path '*/__pycache__/*' \
      ! -path '*/.pytest_cache/*' \
      ! -path '*/.mypy_cache/*' \
      ! -path '*/.ruff_cache/*' \
      -print0
  )

  while IFS= read -r -d '' tracked_path; do
    case "$tracked_path" in
      "Tasks/$task_name/cluster_runs/"*) continue ;;
    esac
    source_file="$REPO_ROOT/$tracked_path"
    [[ -f "$source_file" ]] || continue
    relative_path=${source_file#"$task_dir"/}
    copy_file "$source_file" "$destination_root/$relative_path"
  done < <(
    git -C "$REPO_ROOT" ls-files -z -- "Tasks/$task_name"
  )
}

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)

task_name=
run_id=
include_run=auto
run_option=
pr_title=
summary_text=
dry_run=false
declare -a include_paths=()

while (($#)); do
  case "$1" in
    --task)
      require_value "$1" "$#"
      task_name=$2
      shift 2
      ;;
    --run-id)
      require_value "$1" "$#"
      if [[ "$run_option" == "no-run" ]]; then
        echo "--run-id cannot be combined with --no-run." >&2
        exit 2
      fi
      run_id=$2
      include_run=selected
      run_option=run-id
      shift 2
      ;;
    --no-run)
      if [[ "$run_option" == "run-id" ]]; then
        echo "--no-run cannot be combined with --run-id." >&2
        exit 2
      fi
      include_run=false
      run_option=no-run
      shift
      ;;
    --include)
      require_value "$1" "$#"
      include_paths+=("$2")
      shift 2
      ;;
    --summary)
      require_value "$1" "$#"
      summary_text=$2
      shift 2
      ;;
    --title)
      require_value "$1" "$#"
      pr_title=$2
      shift 2
      ;;
    --dry-run)
      dry_run=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$task_name" ]]; then
  echo "--task is required." >&2
  usage >&2
  exit 2
fi

if [[ "$task_name" == */* || "$task_name" == "." || "$task_name" == ".." ]]; then
  echo "Task must be one folder name under Master/Tasks." >&2
  exit 2
fi

safe_task=$(slug "$task_name")
if [[ -z "$safe_task" ]]; then
  echo "Task name must contain letters or numbers." >&2
  exit 2
fi

task_dir="$REPO_ROOT/Tasks/$task_name"
if [[ ! -d "$task_dir" ]]; then
  echo "Task directory not found: $task_dir" >&2
  echo "Available tasks:" >&2
  find "$REPO_ROOT/Tasks" -mindepth 1 -maxdepth 1 -type d \
    -exec basename {} \; |
    sort |
    sed 's/^/  /' >&2
  exit 2
fi
task_dir=$(canonical_directory "$task_dir")

selected_run=
cluster_root="$task_dir/cluster_runs"
if [[ "$include_run" == "selected" ]]; then
  if [[ ! "$run_id" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
    echo "Invalid run ID: $run_id" >&2
    exit 2
  fi
  selected_run="$cluster_root/$run_id"
  if [[ ! -d "$selected_run" ]]; then
    echo "Cluster run not found: $selected_run" >&2
    exit 2
  fi
elif [[ "$include_run" == "auto" && -f "$cluster_root/latest_run.txt" ]]; then
  selected_run=$(head -n 1 "$cluster_root/latest_run.txt")
  if [[ "$selected_run" != /* ]]; then
    selected_run="$cluster_root/$selected_run"
  fi
  if [[ ! -d "$selected_run" ]]; then
    echo "Latest cluster run does not exist: $selected_run" >&2
    echo "Use --no-run or provide --run-id explicitly." >&2
    exit 2
  fi
fi

if [[ -n "$selected_run" ]]; then
  cluster_root=$(canonical_directory "$cluster_root")
  selected_run=$(canonical_directory "$selected_run")
  case "$selected_run/" in
    "$cluster_root/"*) ;;
    *)
      echo "Selected run is outside the task's cluster_runs directory." >&2
      exit 2
      ;;
  esac
  run_id=$(basename "$selected_run")
fi

declare -a resolved_includes=()
if ((${#include_paths[@]} > 0)); then
  for include_path in "${include_paths[@]}"; do
    if [[ "$include_path" != /* ]]; then
      include_path="$REPO_ROOT/$include_path"
    fi
    if [[ ! -e "$include_path" ]]; then
      echo "Included path not found: $include_path" >&2
      exit 2
    fi
    if [[ -d "$include_path" ]]; then
      resolved_path=$(canonical_directory "$include_path")
    else
      resolved_path=$(canonical_file "$include_path")
    fi
    assert_inside_repo "$resolved_path"
    case "$resolved_path" in
      "$REPO_ROOT/.git"|"$REPO_ROOT/.git"/*)
        echo "The repository .git directory cannot be included." >&2
        exit 2
        ;;
    esac
    resolved_includes+=("$resolved_path")
  done
fi

for required_command in git gzip; do
  if ! command -v "$required_command" >/dev/null 2>&1; then
    echo "Required command not found: $required_command" >&2
    exit 2
  fi
done

origin_url=$(git -C "$REPO_ROOT" remote get-url origin)
normalized_origin=$(
  printf '%s' "$origin_url" |
    sed -E \
      's#^git@github.com:#github.com/#; s#^https?://##; s#\.git$##'
)
if [[ "$normalized_origin" != "github.com/yakovelmaleh/Master" ]]; then
  echo "This utility may run only in github.com/yakovelmaleh/Master." >&2
  echo "Current origin: $origin_url" >&2
  exit 2
fi

timestamp=$(date +"%Y%m%d-%H%M%S")
summary_id="${safe_task:0:60}-$timestamp"
branch_name="user/yakovelmaleh/summarize-$summary_id"
temporary_root=$(mktemp -d "${TMPDIR:-/tmp}/master-task-summary.XXXXXX")
stage_destination="$temporary_root/$summary_id"
pr_worktree="$temporary_root/worktree"

cleanup() {
  if [[ -d "$pr_worktree" ]]; then
    git -C "$REPO_ROOT" worktree remove --force "$pr_worktree" \
      >/dev/null 2>&1 || true
  fi
  rm -rf -- "$temporary_root"
  if [[ "$dry_run" == false ]]; then
    git -C "$REPO_ROOT" switch main >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

artifacts_dir="$stage_destination/artifacts"
mkdir -p "$artifacts_dir/task"
copy_task_definition "$artifacts_dir/task"

if [[ -n "$selected_run" ]]; then
  copy_tree "$selected_run" "$artifacts_dir/cluster-run"
fi

if ((${#resolved_includes[@]} > 0)); then
  for resolved_path in "${resolved_includes[@]}"; do
    relative_path=${resolved_path#"$REPO_ROOT"/}
    if [[ -d "$resolved_path" ]]; then
      copy_tree "$resolved_path" "$artifacts_dir/included/$relative_path"
    else
      copy_file "$resolved_path" "$artifacts_dir/included/$relative_path"
    fi
  done
fi

sensitive_names=$(
  find "$artifacts_dir" -type f \
    \( \
      -name '.env' -o \
      -name '*.pfx' -o \
      -name '*.p12' -o \
      -name '*.pem' -o \
      -name '*.key' -o \
      -name 'id_rsa' -o \
      -name 'id_ed25519' \
    \) \
    -print
)
if [[ -n "$sensitive_names" ]]; then
  echo "Sensitive file names were found; refusing to create the PR:" >&2
  echo "$sensitive_names" >&2
  exit 2
fi

secret_matches=$(
  grep -RIlE \
    '(-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----|Authorization:[[:space:]]*(Bearer|Basic)[[:space:]]+[A-Za-z0-9._~+/-]{20,}|(JIRA_TOKEN|GITHUB_TOKEN|GH_TOKEN|AWS_SECRET_ACCESS_KEY)[=:][^[:space:]]{8,}|gh[pousr]_[A-Za-z0-9]{20,})' \
    "$artifacts_dir" || true
)
if [[ -n "$secret_matches" ]]; then
  echo "Possible credentials were found; refusing to create the PR:" >&2
  echo "$secret_matches" >&2
  exit 2
fi

while IFS= read -r -d '' large_file; do
  gzip -9 "$large_file"
done < <(find "$artifacts_dir" -type f -size +90M -print0)

oversized_files=$(find "$artifacts_dir" -type f -size +95M -print)
if [[ -n "$oversized_files" ]]; then
  echo "Files remain above GitHub's safe per-file size after compression:" >&2
  echo "$oversized_files" >&2
  exit 2
fi

(
  cd "$stage_destination"
  find artifacts -type f -print | sort > FILES.txt
)
file_count=$(wc -l < "$stage_destination/FILES.txt" | tr -d ' ')
bundle_kib=$(du -sk "$artifacts_dir" | awk '{print $1}')
source_branch=$(git -C "$REPO_ROOT" branch --show-current)
source_commit=$(git -C "$REPO_ROOT" rev-parse HEAD)

cat > "$stage_destination/README.md" <<EOF
# Task summary: $task_name

This folder is a review bundle generated from the cluster checkout. It copies
the selected task files into this summary folder; merging the PR does not
overwrite the original task implementation or runtime directories.

## Source

- Task: \`$task_name\`
- Original task directory: \`$task_dir\`
- Source branch: \`${source_branch:-detached}\`
- Source commit: \`$source_commit\`
- Bundle created: \`$(date -u +"%Y-%m-%dT%H:%M:%SZ")\`
- Included files: \`$file_count\`
- Bundle size: \`${bundle_kib} KiB\`
EOF

if [[ -n "$selected_run" ]]; then
  cat >> "$stage_destination/README.md" <<EOF
- Cluster run: \`$run_id\`
- Original cluster run directory: \`$selected_run\`
EOF
else
  cat >> "$stage_destination/README.md" <<'EOF'
- Cluster run: not included
EOF
fi

cat >> "$stage_destination/README.md" <<'EOF'

## Included content

- `artifacts/task/` contains the task definition and tracked task files.
- `artifacts/cluster-run/` contains the selected cluster run, when present.
- `artifacts/included/` contains paths supplied with `--include`, when present.
- `FILES.txt` is the exact committed file inventory.

Runtime caches, Python bytecode, and unrelated historical cluster runs are not
included automatically. Files larger than 90 MiB are gzip-compressed.
EOF

if [[ -n "$summary_text" ]]; then
  cat >> "$stage_destination/README.md" <<EOF

## Submitted summary

$summary_text
EOF
fi

echo "Task: $task_name"
echo "Task directory: $task_dir"
if [[ -n "$selected_run" ]]; then
  echo "Cluster run: $run_id"
else
  echo "Cluster run: not included"
fi
echo "Included files: $file_count"
echo "Bundle size: ${bundle_kib} KiB"

if [[ "$dry_run" == true ]]; then
  echo
  echo "Dry run complete. Files that would be committed:"
  cat "$stage_destination/FILES.txt"
  exit 0
fi

current_branch=$(git -C "$REPO_ROOT" branch --show-current)
if [[ "$current_branch" != "main" ]]; then
  if ! git -C "$REPO_ROOT" diff --quiet ||
    ! git -C "$REPO_ROOT" diff --cached --quiet; then
    echo "The Master checkout has tracked changes on '$current_branch'." >&2
    echo "Switch to main without losing those changes, then rerun." >&2
    exit 2
  fi
  git -C "$REPO_ROOT" switch main
fi

git -C "$REPO_ROOT" fetch origin main

create_pr_automatically=false
if command -v gh >/dev/null 2>&1 &&
  gh auth status >/dev/null 2>&1; then
  create_pr_automatically=true
else
  echo "GitHub CLI is unavailable or not authenticated."
  echo "The summary branch will be pushed and a PR link will be printed."
fi

git -C "$REPO_ROOT" worktree add \
  -b "$branch_name" \
  "$pr_worktree" \
  origin/main

destination="$pr_worktree/Tasks/task-summaries/$summary_id"
mkdir -p "$(dirname "$destination")"
cp -Rp "$stage_destination" "$destination"

git -C "$pr_worktree" add -f "Tasks/task-summaries/$summary_id"
git -C "$pr_worktree" commit \
  -m "Add $task_name task summary" \
  -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>" \
  -m "Created-by: Tasks/create-task-summary-pr/create_task_summary_pr.sh"
git -C "$pr_worktree" push -u origin "$branch_name"

if [[ -z "$pr_title" ]]; then
  pr_title="Summarize task: $task_name"
fi

if [[ "$create_pr_automatically" == true ]]; then
  pr_url=$(
    gh pr create \
      --repo yakovelmaleh/Master \
      --base main \
      --head "$branch_name" \
      --title "$pr_title" \
      --body-file "$destination/README.md"
  )
  echo "Task summary PR: $pr_url"
else
  encoded_branch=${branch_name//\//%2F}
  pr_url="https://github.com/yakovelmaleh/Master/compare/main...$encoded_branch?expand=1"
  echo "Task summary branch pushed: $branch_name"
  echo "Create the PR here: $pr_url"
fi

echo "Primary checkout branch: $(git -C "$REPO_ROOT" branch --show-current)"
