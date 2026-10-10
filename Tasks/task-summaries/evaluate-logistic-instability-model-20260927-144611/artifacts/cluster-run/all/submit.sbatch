#!/bin/bash
#SBATCH --partition=main
#SBATCH --time=4-03:30:00
#SBATCH --job-name=evaluate-logistic-instability-model-all
#SBATCH --output=/home/yakovelm/Master/Tasks/evaluate-logistic-instability-model/cluster_runs/20260924-212357-961761/all/logs/job-%J.out
#SBATCH --mail-user=yakovelm@post.bgu.ac.il
#SBATCH --mail-type=ALL
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=6
#SBATCH --mem=16G
set -euo pipefail
echo "SLURM_JOB_ID=${SLURM_JOB_ID:-unknown} NODE=${SLURM_JOB_NODELIST:-unknown}"
echo "Project: all; levels: 5,10,15,20"
module load anaconda
source activate master
export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-6}
export OPENBLAS_NUM_THREADS=${SLURM_CPUS_PER_TASK:-6}
export MKL_NUM_THREADS=${SLURM_CPUS_PER_TASK:-6}
cd /home/yakovelm/Master
python /home/yakovelm/Master/Tasks/verify-refactored-instability-model/run_verification.py --datasets-file /home/yakovelm/Master/Tasks/evaluate-logistic-instability-model/cluster_runs/20260924-212357-961761/datasets.json --comparison-config /home/yakovelm/Master/Tasks/evaluate-logistic-instability-model/cluster_runs/20260924-212357-961761/comparison_config.json --protocol pooled --experiment logistic --project all --models RF XGboost NN --output-root /home/yakovelm/Master/Tasks/evaluate-logistic-instability-model/cluster_runs/20260924-212357-961761/all/results --label-threshold 5 --label-threshold 10 --label-threshold 15 --label-threshold 20
