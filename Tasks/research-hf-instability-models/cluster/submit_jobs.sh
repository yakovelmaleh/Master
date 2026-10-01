#!/usr/bin/env bash
set -euo pipefail
TASKS=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
exec python3 "$TASKS/train-hf-instability-within-project/cluster/submit_jobs.py" research "$@"
