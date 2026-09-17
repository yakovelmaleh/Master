#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Create a GitHub investigation PR for one dataset from one cluster task.

Usage:
  ./create_investigation_pr.sh \
    --task TASK_NAME \
    --dataset DATASET_NAME \
    [--run-id RUN_ID] \
    [--title PR_TITLE] \
    [--dry-run]

Required:
  --task NAME       Task folder under Master/Tasks.
  --dataset NAME    Dataset/source directory within the selected cluster run.

Optional:
  --run-id ID       Cluster run ID; defaults to cluster_runs/latest_run.txt.
  --title TEXT      PR title; defaults to an investigation title.
  --dry-run         Validate and display selected artifacts without Git changes.
  -h, --help        Show this help.
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

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)

task_name=
dataset_name=
run_id=
pr_title=
dry_run=false

while (($#)); do
  case "$1" in
    --task)
      task_name=$2
      shift 2
      ;;
    --dataset)
      dataset_name=$2
      shift 2
      ;;
    --run-id)
      run_id=$2
      shift 2
      ;;
    --title)
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

if [[ -z "$task_name" || -z "$dataset_name" ]]; then
  echo "--task and --dataset are required." >&2
  usage >&2
  exit 2
fi

safe_task=$(slug "$task_name")
safe_dataset=$(slug "$dataset_name")
if [[ -z "$safe_task" || -z "$safe_dataset" ]]; then
  echo "Task and dataset names must contain letters or numbers." >&2
  exit 2
fi

task_dir="$REPO_ROOT/Tasks/$task_name"
cluster_root="$task_dir/cluster_runs"
if [[ ! -d "$cluster_root" ]]; then
  echo "Cluster results directory not found: $cluster_root" >&2
  exit 2
fi

cluster_root=$(canonical_directory "$cluster_root")
if [[ -z "$run_id" ]]; then
  latest_file="$cluster_root/latest_run.txt"
  if [[ ! -f "$latest_file" ]]; then
    echo "Latest-run pointer not found: $latest_file" >&2
    echo "Provide --run-id explicitly." >&2
    exit 2
  fi
  run_root=$(head -n 1 "$latest_file")
  if [[ "$run_root" != /* ]]; then
    run_root="$cluster_root/$run_root"
  fi
else
  if [[ ! "$run_id" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
    echo "Invalid run ID: $run_id" >&2
    exit 2
  fi
  run_root="$cluster_root/$run_id"
fi

if [[ ! -d "$run_root" ]]; then
  echo "Cluster run not found: $run_root" >&2
  exit 2
fi
run_root=$(canonical_directory "$run_root")
case "$run_root/" in
  "$cluster_root/"*) ;;
  *)
    echo "Selected run is outside the task's cluster_runs directory." >&2
    exit 2
    ;;
esac

run_id=$(basename "$run_root")
dataset_root="$run_root/$safe_dataset"
if [[ ! -d "$dataset_root" ]]; then
  dataset_root=
  for candidate in "$run_root"/*; do
    [[ -d "$candidate" ]] || continue
    if [[ "$(slug "$(basename "$candidate")")" == "$safe_dataset" ]]; then
      dataset_root=$candidate
      break
    fi
  done
fi

if [[ -z "$dataset_root" || ! -d "$dataset_root" ]]; then
  echo "Dataset '$dataset_name' was not found under: $run_root" >&2
  echo "Available dataset directories:" >&2
  for candidate in "$run_root"/*; do
    [[ -d "$candidate" ]] || continue
    echo "  $(basename "$candidate")" >&2
  done
  exit 2
fi
dataset_root=$(canonical_directory "$dataset_root")

results_dir="$dataset_root/results"
logs_dir="$dataset_root/logs"
sbatch_file="$dataset_root/submit.sbatch"
run_manifest="$run_root/submitted_jobs.tsv"

if [[ ! -d "$results_dir" ]]; then
  echo "Results directory not found: $results_dir" >&2
  exit 2
fi

if [[ ! -d "$logs_dir" ]]; then
  echo "Logs directory not found: $logs_dir" >&2
  exit 2
fi

log_count=$(find "$logs_dir" -type f -name '*.out' | wc -l | tr -d ' ')
if [[ "$log_count" == 0 ]]; then
  echo "No .out logs were found under: $logs_dir" >&2
  exit 2
fi

dataset_count=$(
  find -L "$results_dir" \
    -type f \
    -name 'features_labels_table_os.csv' |
    wc -l |
    tr -d ' '
)
configured_dataset=
if [[ "$dataset_count" == 0 && -f "$task_dir/datasets.json" ]]; then
  if ! command -v jq >/dev/null 2>&1; then
    echo "jq is required to resolve the configured dataset path." >&2
    exit 2
  fi
  configured_dataset=$(
    jq -r \
      --arg dataset "$dataset_name" \
      '
        to_entries[]
        | select(
            (.key | ascii_downcase)
            == ($dataset | ascii_downcase)
          )
        | .value
      ' \
      "$task_dir/datasets.json" |
      head -n 1
  )
  if [[ -n "$configured_dataset" && "$configured_dataset" != "null" ]]; then
    if [[ "$configured_dataset" != /* ]]; then
      configured_dataset="$REPO_ROOT/$configured_dataset"
    fi
    if [[ ! -f "$configured_dataset" ]]; then
      echo "Configured dataset was not found: $configured_dataset" >&2
      exit 2
    fi
    dataset_count=1
  fi
fi

if [[ "$dataset_count" == 0 ]]; then
  echo "No complete features_labels_table_os.csv dataset was found." >&2
  echo "The job may have failed before dataset creation." >&2
  exit 2
fi

echo "Task: $task_name"
echo "Run: $run_id"
echo "Dataset: $dataset_name"
echo "Results: $results_dir"
echo "Logs: $logs_dir"
echo "Dataset CSV files found: $dataset_count"

if [[ "$dry_run" == true ]]; then
  echo
  echo "Files that would be included:"
  find -L "$results_dir" "$logs_dir" -type f -print | sort
  [[ -f "$sbatch_file" ]] && echo "$sbatch_file"
  [[ -f "$run_manifest" ]] && echo "$run_manifest"
  [[ -n "$configured_dataset" ]] && echo "$configured_dataset"
  exit 0
fi

for required_command in git gzip; do
  if ! command -v "$required_command" >/dev/null 2>&1; then
    echo "Required command not found: $required_command" >&2
    exit 2
  fi
done

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
  echo "The investigation branch will be pushed and a PR link will be printed."
fi

timestamp=$(date +"%Y%m%d-%H%M%S")
investigation_id="${safe_task:0:35}-${safe_dataset:0:35}-${run_id:0:30}-$timestamp"
branch_name="user/yakovelmaleh/investigate-$investigation_id"
temporary_root=$(mktemp -d "${TMPDIR:-/tmp}/master-investigation.XXXXXX")
pr_worktree="$temporary_root/worktree"

cleanup() {
  if [[ -d "$pr_worktree" ]]; then
    git -C "$REPO_ROOT" worktree remove --force "$pr_worktree" \
      >/dev/null 2>&1 || true
  fi
  rmdir "$temporary_root" >/dev/null 2>&1 || true
  git -C "$REPO_ROOT" switch main >/dev/null 2>&1 || true
}
trap cleanup EXIT

git -C "$REPO_ROOT" fetch origin main
git -C "$REPO_ROOT" worktree add \
  -b "$branch_name" \
  "$pr_worktree" \
  origin/main

destination="$pr_worktree/Tasks/investigations/$investigation_id"
artifacts_dir="$destination/artifacts"
mkdir -p "$artifacts_dir"
cp -RL "$results_dir" "$artifacts_dir/results"
cp -RL "$logs_dir" "$artifacts_dir/logs"
[[ -f "$sbatch_file" ]] && cp "$sbatch_file" "$artifacts_dir/submit.sbatch"
[[ -f "$run_manifest" ]] &&
  cp "$run_manifest" "$artifacts_dir/submitted_jobs.tsv"

if [[ -n "$configured_dataset" ]]; then
  mkdir -p "$artifacts_dir/dataset"
  cp "$configured_dataset" \
    "$artifacts_dir/dataset/features_labels_table_os.csv"
fi

copied_dataset_count=$(
  find "$artifacts_dir" \
    -type f \
    -name 'features_labels_table_os.csv' |
    wc -l |
    tr -d ' '
)
if [[ "$copied_dataset_count" == 0 ]]; then
  echo "The investigation bundle does not contain the required dataset." >&2
  exit 2
fi

declare -a secret_scan_paths=()
[[ -d "$artifacts_dir/logs" ]] &&
  secret_scan_paths+=("$artifacts_dir/logs")
[[ -f "$artifacts_dir/submit.sbatch" ]] &&
  secret_scan_paths+=("$artifacts_dir/submit.sbatch")
[[ -f "$artifacts_dir/submitted_jobs.tsv" ]] &&
  secret_scan_paths+=("$artifacts_dir/submitted_jobs.tsv")
while IFS= read -r -d '' metadata_file; do
  secret_scan_paths+=("$metadata_file")
done < <(
  find "$artifacts_dir/results" \
    -type f \
    \( -name '*.json' -o -name '*.txt' -o -name '*.log' \) \
    ! -path '*/raw/*' \
    -print0
)

secret_matches=
if ((${#secret_scan_paths[@]} > 0)); then
  secret_matches=$(
    grep -RIlE \
      '(Authorization:[[:space:]]*(Bearer|Basic)[[:space:]]+[A-Za-z0-9._~+/-]{20,}|(JIRA_TOKEN|GITHUB_TOKEN|GH_TOKEN)[=:][^[:space:]]{8,})' \
      "${secret_scan_paths[@]}" || true
  )
fi
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

cat > "$destination/README.md" <<EOF
# Investigation: $task_name / $dataset_name

This folder contains the complete investigation bundle for one cluster
dataset run.

## Source

- Task: \`$task_name\`
- Dataset: \`$dataset_name\`
- Cluster run: \`$run_id\`
- Original run directory: \`$run_root\`
- Original dataset directory: \`$dataset_root\`
- Bundle created: \`$(date -u +"%Y-%m-%dT%H:%M:%SZ")\`

## Included artifacts

- The complete \`results/\` directory for this dataset.
- All available SLURM \`.out\` logs.
- The generated \`submit.sbatch\` file, when present.
- The run-level \`submitted_jobs.tsv\` manifest, when present.
- At least one complete \`features_labels_table_os.csv\` dataset.

Files larger than 90 MiB are gzip-compressed before committing. This PR is
for investigation only; it does not change model or pipeline behavior.
EOF

(
  cd "$destination"
  find artifacts -type f -print | sort > FILES.txt
)

git -C "$pr_worktree" add "Tasks/investigations/$investigation_id"
git -C "$pr_worktree" commit \
  -m "Add $dataset_name investigation artifacts" \
  -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>" \
  -m "Created-by: Tasks/create-investigation-pr/create_investigation_pr.sh"
git -C "$pr_worktree" push -u origin "$branch_name"

if [[ -z "$pr_title" ]]; then
  pr_title="Investigate $dataset_name failure in $task_name"
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
  echo "Investigation PR: $pr_url"
else
  encoded_branch=${branch_name//\//%2F}
  pr_url="https://github.com/yakovelmaleh/Master/compare/main...$encoded_branch?expand=1"
  echo "Investigation branch pushed: $branch_name"
  echo "Create the PR here: $pr_url"
fi

echo "Primary checkout branch: $(git -C "$REPO_ROOT" branch --show-current)"
