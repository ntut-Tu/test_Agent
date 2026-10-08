#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
    printf 'Usage: %s <producer-fixture-directory>\n' "$0" >&2
    exit 2
fi
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec uv run --project "$PROJECT_ROOT" --locked python "$PROJECT_ROOT/tests/verify_java_trace_spike.py" "$1"
