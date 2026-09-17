#!/bin/bash

#SBATCH --partition=main
#SBATCH --time=4-03:30:00
#SBATCH --job-name=jira-jira
#SBATCH --output=/home/yakovelm/Master/Tasks/jira-url-to-instability-model/cluster_runs/20260917-204018/jira/logs/job-%J.out
#SBATCH --tasks=2
#SBATCH --cpus-per-task=6
#SBATCH --mail-user=yakovelm@post.bgu.ac.il
#SBATCH --mail-type=ALL
#SBATCH --mem=16G

set -euo pipefail

echo "$(date)"
echo -e "\nSLURM_JOBID:\t\t${SLURM_JOBID:-unknown}"
echo -e "SLURM_JOB_NODELIST:\t${SLURM_JOB_NODELIST:-unknown}\n"
echo "Source: Jira"
echo "Results: /home/yakovelm/Master/Tasks/jira-url-to-instability-model/cluster_runs/20260917-204018/jira/results"
echo "Log: /home/yakovelm/Master/Tasks/jira-url-to-instability-model/cluster_runs/20260917-204018/jira/logs/job-${SLURM_JOB_ID:-unknown}.out"

module load anaconda
source activate master
cd /home/yakovelm/Master/Tasks/jira-url-to-instability-model
python /home/yakovelm/Master/Tasks/jira-url-to-instability-model/cluster/run_cluster.py --sources-file /home/yakovelm/Master/Source/jira_data_for_instability_cluster.json --only Jira --output-root /home/yakovelm/Master/Tasks/jira-url-to-instability-model/cluster_runs/20260917-204018/jira/results --refresh 
