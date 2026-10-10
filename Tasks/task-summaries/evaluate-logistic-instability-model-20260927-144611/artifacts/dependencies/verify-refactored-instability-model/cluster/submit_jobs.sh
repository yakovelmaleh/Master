#!/usr/bin/env bash
set -euo pipefail
TASK_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
exec python3 "$TASK_DIR/cluster/submit_jobs.py" --task-dir "$TASK_DIR" --protocol pooled "$@"
