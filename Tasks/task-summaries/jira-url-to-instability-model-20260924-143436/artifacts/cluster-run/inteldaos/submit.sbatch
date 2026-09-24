#!/bin/bash

#SBATCH --partition=main
#SBATCH --time=4-03:30:00
#SBATCH --job-name=jira-inteldaos
#SBATCH --output=/home/yakovelm/Master/Tasks/jira-url-to-instability-model/cluster_runs/20260917-223051/inteldaos/logs/job-%J.out
#SBATCH --tasks=2
#SBATCH --cpus-per-task=6
#SBATCH --mail-user=yakovelm@post.bgu.ac.il
#SBATCH --mail-type=ALL
#SBATCH --mem=16G

set -euo pipefail

echo "$(date)"
echo -e "\nSLURM_JOBID:\t\t${SLURM_JOBID:-unknown}"
echo -e "SLURM_JOB_NODELIST:\t${SLURM_JOB_NODELIST:-unknown}\n"
echo "Source: IntelDAOS"
echo "Results: /home/yakovelm/Master/Tasks/jira-url-to-instability-model/cluster_runs/20260917-223051/inteldaos/results"
echo "Log: /home/yakovelm/Master/Tasks/jira-url-to-instability-model/cluster_runs/20260917-223051/inteldaos/logs/job-${SLURM_JOB_ID:-unknown}.out"

module load anaconda
source activate master
cd /home/yakovelm/Master/Tasks/jira-url-to-instability-model
python /home/yakovelm/Master/Tasks/jira-url-to-instability-model/cluster/run_cluster.py --sources-file /home/yakovelm/Master/Source/jira_data_for_instability_cluster.json --only IntelDAOS --output-root /home/yakovelm/Master/Tasks/jira-url-to-instability-model/cluster_runs/20260917-223051/inteldaos/results --only Qt --refresh 
