#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASK_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Prefer the solution bundled with this task; fall back to Harbor's /solution mount.
if [[ -f "$SCRIPT_DIR/reference_solution.py" ]]; then
    SOLUTION_PY="$SCRIPT_DIR/reference_solution.py"
elif [[ -f "/solution/reference_solution.py" ]]; then
    SOLUTION_PY="/solution/reference_solution.py"
else
    echo "Could not locate reference_solution.py" >&2
    exit 1
fi

if [[ -n "${OUTPUT_DIR:-}" ]]; then
    rm -rf "$OUTPUT_DIR"
    mkdir -p "$OUTPUT_DIR"
elif [[ -d "/app/data" ]]; then
    rm -rf /app/outputs
    mkdir -p /app/outputs
else
    export OUTPUT_DIR="$TASK_DIR/outputs"
    rm -rf "$OUTPUT_DIR"
    mkdir -p "$OUTPUT_DIR"
fi

python3 "$SOLUTION_PY"
