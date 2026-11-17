#!/usr/bin/env bash
set -euo pipefail
TASK_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
exec "$HOME/.conda/envs/master-openai/bin/python" "$TASK_DIR/run_experiment.py" "$@"
