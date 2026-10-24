#!/usr/bin/env bash
#SBATCH --job-name=master-openai-storage-probe
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=1G
#SBATCH --time=00:10:00
set -euo pipefail
umask 077

storage=${1:?Supply the existing external study storage directory}
python_bin=${2:?Supply the absolute master-openai Python executable}
repo=${SLURM_SUBMIT_DIR:?Submit this script from the Master repository}
admin="$repo/Tasks/train-openai-instability-within-project/control_admin.py"
directory=$(mktemp -d "$storage/cloud-probe.${SLURM_JOB_ID:?}.XXXXXX")
nodes=()
while IFS= read -r node; do nodes+=("$node"); done < <(scontrol show hostnames "$SLURM_JOB_NODELIST")
if [[ ${#nodes[@]} -ne 2 || "${nodes[0]}" == "${nodes[1]}" ]]; then
  echo 'CLOUD_CONTROL_PROBE_FAILED: two distinct compute nodes are required.' >&2
  exit 1
fi

srun --exclusive --nodes=1 --ntasks=1 --nodelist="${nodes[0]}" \
  "$python_bin" "$admin" probe --storage "$storage" --output "$directory/atomic.json"
srun --exclusive --nodes=1 --ntasks=1 --nodelist="${nodes[0]}" \
  "$python_bin" "$admin" lease-hold --storage "$storage" --output "$directory/holder.json" &
holder_pid=$!
printf 'Waiting for lease-holder readiness (up to 180 seconds).\n'
for ((attempt=0; attempt<180; attempt++)); do
  [[ -f "$directory/holder.json" ]] && break
  sleep 1
done
if [[ ! -f "$directory/holder.json" ]]; then
  echo 'CLOUD_CONTROL_PROBE_FAILED: lease-holder readiness timed out after 180 seconds; inspect the holder step logs.' >&2
  exit 1
fi
srun --exclusive --nodes=1 --ntasks=1 --nodelist="${nodes[1]}" \
  "$python_bin" "$admin" lease-contend --storage "$storage" \
  --holding "$directory/holder.json" --output "$directory/contender.json"
wait "$holder_pid"
printf 'CLOUD_CONTROL_PROBE_PASSED: %s\n' "$directory"
