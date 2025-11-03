#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGET_FILE="$PROJECT_ROOT/backend/app/services/exports/pytest_exporter.py"

if [ ! -f "$TARGET_FILE" ]; then
    echo "pytest_exporter module not found at $TARGET_FILE" >&2
    exit 1
fi

python -m py_compile "$TARGET_FILE"
