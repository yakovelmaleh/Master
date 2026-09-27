#!/bin/bash
#SBATCH --partition=main
#SBATCH --time=4-03:30:00
#SBATCH --job-name=validate-refactored-model-per-datas-apache
#SBATCH --output=/home/yakovelm/Master/Tasks/validate-refactored-model-per-dataset/cluster_runs/20260924-212251-041726/apache/logs/job-%J.out
#SBATCH --mail-user=yakovelm@post.bgu.ac.il
#SBATCH --mail-type=ALL
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=6
#SBATCH --mem=16G
set -euo pipefail
echo "SLURM_JOB_ID=${SLURM_JOB_ID:-unknown} NODE=${SLURM_JOB_NODELIST:-unknown}"
echo "Project: Apache; levels: 5,10,15,20"
module load anaconda
source activate master
export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-6}
export OPENBLAS_NUM_THREADS=${SLURM_CPUS_PER_TASK:-6}
export MKL_NUM_THREADS=${SLURM_CPUS_PER_TASK:-6}
cd /home/yakovelm/Master
python /home/yakovelm/Master/Tasks/verify-refactored-instability-model/run_verification.py --datasets-file /home/yakovelm/Master/Tasks/validate-refactored-model-per-dataset/cluster_runs/20260924-212251-041726/datasets.json --comparison-config /home/yakovelm/Master/Tasks/validate-refactored-model-per-dataset/cluster_runs/20260924-212251-041726/comparison_config.json --protocol within-project --experiment comparison --project Apache --models RF XGboost NN --output-root /home/yakovelm/Master/Tasks/validate-refactored-model-per-dataset/cluster_runs/20260924-212251-041726/apache/results --label-threshold 5 --label-threshold 10 --label-threshold 15 --label-threshold 20
