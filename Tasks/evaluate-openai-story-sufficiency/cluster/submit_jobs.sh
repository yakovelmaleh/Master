#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
exec "$HOME/.conda/envs/master-openai/bin/python" "$SCRIPT_DIR/submit_jobs.py" "$@"
