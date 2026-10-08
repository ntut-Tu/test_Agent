#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec uv run --project "$PROJECT_ROOT" --locked python "$PROJECT_ROOT/scripts/register_traefik_route.py" "$@"
