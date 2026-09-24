#!/bin/bash

#SBATCH --partition=main
#SBATCH --time=4-03:30:00
#SBATCH --job-name=validate-qt
#SBATCH --output=/home/yakovelm/Master/Tasks/validate-refactored-model-per-dataset/cluster_runs/20260917-204655/qt/logs/job-%J.out
#SBATCH --tasks=2
#SBATCH --cpus-per-task=6
#SBATCH --mail-user=yakovelm@post.bgu.ac.il
#SBATCH --mail-type=ALL
#SBATCH --mem=16G

set -euo pipefail

echo "$(date)"
echo -e "\nSLURM_JOBID:\t\t${SLURM_JOBID:-unknown}"
echo -e "SLURM_JOB_NODELIST:\t${SLURM_JOB_NODELIST:-unknown}\n"
echo "Dataset: Qt"
echo "Results: /home/yakovelm/Master/Tasks/validate-refactored-model-per-dataset/cluster_runs/20260917-204655/qt/results"
echo "Log: /home/yakovelm/Master/Tasks/validate-refactored-model-per-dataset/cluster_runs/20260917-204655/qt/logs/job-${SLURM_JOB_ID:-unknown}.out"

module load anaconda
source activate master
cd /home/yakovelm/Master/Tasks/validate-refactored-model-per-dataset
python /home/yakovelm/Master/Tasks/verify-refactored-instability-model/run_verification.py --datasets-file /home/yakovelm/Master/Tasks/validate-refactored-model-per-dataset/datasets.json --project Qt --label-threshold 5 --output-root /home/yakovelm/Master/Tasks/validate-refactored-model-per-dataset/cluster_runs/20260917-204655/qt/results 
