#!/usr/bin/env bash
set -uo pipefail

mkdir -p /logs/verifier

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -d "$SCRIPT_DIR" ]]; then
    TEST_TARGET="$SCRIPT_DIR"
elif [[ -d "/tests" ]]; then
    TEST_TARGET="/tests"
else
    echo "Could not locate tests directory" >&2
    echo 0 > /logs/verifier/reward.txt
    exit 0
fi

export DATA_DIR="${DATA_DIR:-/app/data}"
export OUTPUT_DIR="${OUTPUT_DIR:-/app/outputs}"

pytest "$TEST_TARGET" -v -rA --ctrf /logs/verifier/ctrf-report.json
if [ $? -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi

exit 0
