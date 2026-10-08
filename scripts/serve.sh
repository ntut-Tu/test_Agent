#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$PROJECT_ROOT"
exec uv run --locked uvicorn codebase_analysis.server:create_app --factory --host 0.0.0.0 --port 8080 --workers 1 --no-proxy-headers
