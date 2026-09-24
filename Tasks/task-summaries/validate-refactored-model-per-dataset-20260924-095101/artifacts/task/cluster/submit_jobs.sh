#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Submit one refactored-model validation job per existing dataset.

Usage:
  ./cluster/submit_jobs.sh [options]

Options:
  --datasets-file PATH  Dataset-path JSON; defaults to ../datasets.json.
  --only PROJECT        Submit only this project; may be repeated.
  --label-threshold N   Instability threshold: 5, 10, 15, or 20.
  --run-id ID           Output batch name; defaults to YYYYmmdd-HHMMSS.
  --conda-env NAME      Conda environment; defaults to master.
  --partition NAME      SLURM partition; defaults to main.
  --time LIMIT          SLURM time limit; defaults to 4-03:30:00.
  --validate-only       Validate and fingerprint inputs without training.
  --dry-run             Generate sbatch files without submitting them.
  -h, --help            Show this help.

Examples:
  ./cluster/submit_jobs.sh
  ./cluster/submit_jobs.sh --only Apache --only Qt
  ./cluster/submit_jobs.sh --dry-run
EOF
}

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TASK_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
MASTER_DIR=$(cd "$TASK_DIR/../.." && pwd)
VERIFICATION_RUNNER=(
  "$MASTER_DIR/Tasks/verify-refactored-instability-model/run_verification.py"
)

datasets_file="$TASK_DIR/datasets.json"
label_threshold=5
run_id=$(date +"%Y%m%d-%H%M%S")
conda_env=master
partition=main
time_limit=4-03:30:00
validate_only=false
dry_run=false
declare -a selected_projects=()

while (($#)); do
  case "$1" in
    --datasets-file)
      datasets_file=$2
      shift 2
      ;;
    --only)
      selected_projects+=("$2")
      shift 2
      ;;
    --label-threshold)
      label_threshold=$2
      shift 2
      ;;
    --run-id)
      run_id=$2
      shift 2
      ;;
    --conda-env)
      conda_env=$2
      shift 2
      ;;
    --partition)
      partition=$2
      shift 2
      ;;
    --time)
      time_limit=$2
      shift 2
      ;;
    --validate-only)
      validate_only=true
      shift
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

if [[ ! -f "$datasets_file" ]]; then
  echo "Datasets file not found: $datasets_file" >&2
  exit 2
fi

if [[ ! -f "${VERIFICATION_RUNNER[0]}" ]]; then
  echo "Verification runner not found: ${VERIFICATION_RUNNER[0]}" >&2
  exit 2
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required to read dataset names." >&2
  exit 2
fi

if ! jq -e 'type == "object" and length > 0' "$datasets_file" >/dev/null; then
  echo "Datasets file must contain a non-empty JSON object." >&2
  exit 2
fi

if [[ ! "$label_threshold" =~ ^(5|10|15|20)$ ]]; then
  echo "Label threshold must be 5, 10, 15, or 20." >&2
  exit 2
fi

if [[ ! "$run_id" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
  echo "Invalid run ID: $run_id" >&2
  exit 2
fi

if [[ ! "$partition" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "Invalid SLURM partition: $partition" >&2
  exit 2
fi

if [[ ! "$time_limit" =~ ^[0-9:-]+$ ]]; then
  echo "Invalid SLURM time limit: $time_limit" >&2
  exit 2
fi

if [[ "$conda_env" == *$'\n'* || -z "$conda_env" ]]; then
  echo "Conda environment must be a non-empty single-line value." >&2
  exit 2
fi

if [[ "$dry_run" == false ]] && ! command -v sbatch >/dev/null 2>&1; then
  echo "sbatch is required unless --dry-run is used." >&2
  exit 2
fi

if ((${#selected_projects[@]} == 0)); then
  while IFS= read -r project; do
    selected_projects+=("$project")
  done < <(jq -r 'keys[]' "$datasets_file")
fi

run_root="$TASK_DIR/cluster_runs/$run_id"
manifest="$run_root/submitted_jobs.tsv"
mkdir -p "$run_root"
printf 'project\tjob_id\tresults\tlog\tsbatch\n' > "$manifest"

for project in "${selected_projects[@]}"; do
  if ! jq -e --arg project "$project" 'has($project)' "$datasets_file" >/dev/null; then
    echo "Project '$project' is not configured in $datasets_file" >&2
    exit 2
  fi

  safe_project=$(
    printf '%s' "$project" |
      tr '[:upper:]' '[:lower:]' |
      sed -E 's/[^a-z0-9._-]+/-/g; s/^-+//; s/-+$//'
  )
  if [[ -z "$safe_project" ]]; then
    echo "Cannot create a safe directory name for project: $project" >&2
    exit 2
  fi

  project_root="$run_root/$safe_project"
  results_dir="$project_root/results"
  logs_dir="$project_root/logs"
  sbatch_file="$project_root/submit.sbatch"
  mkdir -p "$results_dir" "$logs_dir"

  declare -a command_args=(
    python
    "${VERIFICATION_RUNNER[0]}"
    --datasets-file
    "$datasets_file"
    --project
    "$project"
    --label-threshold
    "$label_threshold"
    --output-root
    "$results_dir"
  )
  if [[ "$validate_only" == true ]]; then
    command_args+=(--validate-only)
  fi
  printf -v python_command '%q ' "${command_args[@]}"

  cat > "$sbatch_file" <<EOF
#!/bin/bash

#SBATCH --partition=$partition
#SBATCH --time=$time_limit
#SBATCH --job-name=validate-${safe_project:0:80}
#SBATCH --output=$logs_dir/job-%J.out
#SBATCH --tasks=2
#SBATCH --cpus-per-task=6
#SBATCH --mail-user=yakovelm@post.bgu.ac.il
#SBATCH --mail-type=ALL
#SBATCH --mem=16G

set -euo pipefail

echo "\$(date)"
echo -e "\nSLURM_JOBID:\t\t\${SLURM_JOBID:-unknown}"
echo -e "SLURM_JOB_NODELIST:\t\${SLURM_JOB_NODELIST:-unknown}\n"
echo "Dataset: $project"
echo "Results: $results_dir"
echo "Log: $logs_dir/job-\${SLURM_JOB_ID:-unknown}.out"

module load anaconda
source activate $(printf '%q' "$conda_env")
cd $(printf '%q' "$TASK_DIR")
$python_command
EOF
  chmod +x "$sbatch_file"

  if [[ "$dry_run" == true ]]; then
    job_id=DRY-RUN
    echo "Generated $project validation job: $sbatch_file"
  else
    submission=$(sbatch "$sbatch_file")
    job_id=${submission##* }
    echo "$project validation submitted as job $job_id"
  fi

  printf '%s\t%s\t%s\t%s\t%s\n' \
    "$project" \
    "$job_id" \
    "$results_dir" \
    "$logs_dir/job-%J.out" \
    "$sbatch_file" >> "$manifest"
done

printf '%s\n' "$run_root" > "$TASK_DIR/cluster_runs/latest_run.txt"
echo "Submitted ${#selected_projects[@]} dataset validation job(s)."
echo "Run directory: $run_root"
echo "Job manifest: $manifest"

if [[ "$dry_run" == false ]] && command -v squeue >/dev/null 2>&1; then
  squeue --me
fi
