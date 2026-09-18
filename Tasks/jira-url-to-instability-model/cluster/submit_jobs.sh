#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Submit one independent SLURM job per Jira source.

Usage:
  ./cluster/submit_jobs.sh [launcher options] [run_cluster.py options]

Launcher options:
  --sources-file PATH  Jira source JSON file.
  --only NAME...       Submit jobs only for the named Jira sources.
  --run-id ID          Output batch name; defaults to YYYYmmdd-HHMMSS.
  --conda-env NAME     Conda environment; defaults to master.
  --partition NAME     SLURM partition; defaults to main.
  --time LIMIT         SLURM time limit; defaults to 4-03:30:00.
  --dry-run            Generate files without calling sbatch.
  -h, --help           Show this help.

All other arguments are passed to cluster/run_cluster.py for every source.

Examples:
  ./cluster/submit_jobs.sh --refresh
  ./cluster/submit_jobs.sh --max-issues 100 --refresh
  ./cluster/submit_jobs.sh --sources-file /path/to/sources.json --refresh
EOF
}

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TASK_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
MASTER_DIR=$(cd "$TASK_DIR/../.." && pwd)

sources_file="$MASTER_DIR/Source/jira_data_for_instability_cluster.json"
run_id=$(date +"%Y%m%d-%H%M%S")
conda_env=master
partition=main
time_limit=4-03:30:00
dry_run=false
declare -a pipeline_args=()
declare -a selected_sources=()

while (($#)); do
  case "$1" in
    --sources-file)
      sources_file=$2
      shift 2
      ;;
    --only)
      shift
      selection_start=${#selected_sources[@]}
      while (($#)) && [[ "$1" != --* ]]; do
        selected_sources+=("$1")
        shift
      done
      if ((${#selected_sources[@]} == selection_start)); then
        echo "--only requires at least one source name." >&2
        exit 2
      fi
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
    --dry-run)
      dry_run=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      pipeline_args+=("$@")
      break
      ;;
    *)
      pipeline_args+=("$1")
      shift
      ;;
  esac
done

if [[ ! -f "$sources_file" ]]; then
  echo "Sources file not found: $sources_file" >&2
  exit 2
fi

if [[ ! "$run_id" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
  echo "Run ID may contain only letters, numbers, dots, underscores, and dashes." >&2
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

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required to read Jira source names." >&2
  exit 2
fi

if [[ "$dry_run" == false ]] && ! command -v sbatch >/dev/null 2>&1; then
  echo "sbatch is required unless --dry-run is used." >&2
  exit 2
fi

if ! jq -e 'type == "object" and length > 0' "$sources_file" >/dev/null; then
  echo "Sources file must contain a non-empty JSON object: $sources_file" >&2
  exit 2
fi

declare -a available_sources=()
while IFS= read -r source_name; do
  available_sources+=("$source_name")
done < <(
  jq -r '
    to_entries[]
    | select(
        if (.value | type) == "object"
        then (
          if (.value | has("enabled"))
          then .value.enabled != false
          else true
          end
        )
        else true
        end
      )
    | .key
  ' "$sources_file"
)

declare -a source_names=()
if ((${#selected_sources[@]} == 0)); then
  source_names=("${available_sources[@]}")
else
  for requested_source in "${selected_sources[@]}"; do
    source_found=false
    normalized_requested=$(
      printf '%s' "$requested_source" | tr '[:upper:]' '[:lower:]'
    )
    for available_source in "${available_sources[@]}"; do
      normalized_available=$(
        printf '%s' "$available_source" | tr '[:upper:]' '[:lower:]'
      )
      if [[ "$normalized_requested" == "$normalized_available" ]]; then
        source_found=true
        source_names+=("$available_source")
        break
      fi
    done
    if [[ "$source_found" == false ]]; then
      echo "Requested source was not found or is disabled: $requested_source" >&2
      exit 2
    fi
  done
fi

if ((${#source_names[@]} == 0)); then
  echo "No enabled Jira sources were found in $sources_file" >&2
  exit 2
fi

run_root="$TASK_DIR/cluster_runs/$run_id"
manifest="$run_root/submitted_jobs.tsv"
mkdir -p "$run_root"
printf 'source\tjob_id\tresults\tlog\tsbatch\n' > "$manifest"

source_count=0
for source_name in "${source_names[@]}"; do
  source_count=$((source_count + 1))
  safe_name=$(
    printf '%s' "$source_name" |
      tr '[:upper:]' '[:lower:]' |
      sed -E 's/[^a-z0-9._-]+/-/g; s/^-+//; s/-+$//'
  )
  if [[ -z "$safe_name" ]]; then
    echo "Cannot create a safe directory name for source: $source_name" >&2
    exit 2
  fi

  source_root="$run_root/$safe_name"
  results_dir="$source_root/results"
  logs_dir="$source_root/logs"
  sbatch_file="$source_root/submit.sbatch"
  mkdir -p "$results_dir" "$logs_dir"

  printf -v python_command '%q ' \
    python \
    "$TASK_DIR/cluster/run_cluster.py" \
    --sources-file "$sources_file" \
    --only "$source_name" \
    --output-root "$results_dir" \
    "${pipeline_args[@]}"

  cat > "$sbatch_file" <<EOF
#!/bin/bash

#SBATCH --partition=$partition
#SBATCH --time=$time_limit
#SBATCH --job-name=jira-${safe_name:0:80}
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
echo "Source: $source_name"
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
    echo "Generated $source_name: $sbatch_file"
  else
    submission=$(sbatch "$sbatch_file")
    job_id=${submission##* }
    echo "$source_name submitted as job $job_id"
  fi

  printf '%s\t%s\t%s\t%s\t%s\n' \
    "$source_name" \
    "$job_id" \
    "$results_dir" \
    "$logs_dir/job-%J.out" \
    "$sbatch_file" >> "$manifest"
done

printf '%s\n' "$run_root" > "$TASK_DIR/cluster_runs/latest_run.txt"
echo "Submitted $source_count Jira source job(s)."
echo "Run directory: $run_root"
echo "Job manifest: $manifest"

if [[ "$dry_run" == false ]] && command -v squeue >/dev/null 2>&1; then
  squeue --me
fi
