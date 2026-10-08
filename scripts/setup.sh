#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$PROJECT_ROOT"

if ! command -v uv >/dev/null 2>&1; then
    printf '%s\n' '請先安裝 uv。' >&2
    exit 1
fi

uv sync --locked
if [[ ! -e values.yaml ]]; then
    (umask 077; set -o noclobber; cat values.example.yaml > values.yaml)
    printf '%s\n' '已建立 values.yaml，請填入設定與 secret。'
else
    printf '%s\n' '保留既有 values.yaml。'
fi
