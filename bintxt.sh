#!/usr/bin/env bash
# =============================================================================
# bintxt.sh — Binary ↔ Text truth pipeline
#
# Drop into any repo root alongside bintxt_cfg.yaml. Run with no arguments.
#
# .txt files are the source of truth (version controlled)
# .bin files are inputs or generated artifacts (gitignored by default)
#
# https://github.com/NathanTrudeau/bintxt
# =============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG_FILE="$SCRIPT_DIR/bintxt_cfg.yaml"
EXCLUDE_ARGS=()

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        -f)
            shift
            if [[ $# -eq 0 ]]; then
                echo "ERROR: -f requires a path argument."
                read -rsp $'\nPress any key to exit...' -n 1; echo ""
                exit 1
            fi
            CFG_FILE="$1"
            shift
            ;;
        --exclude)
            shift
            while [[ $# -gt 0 && "$1" != -* && "$1" != --* ]]; do
                EXCLUDE_ARGS+=("$1")
                shift
            done
            ;;
        *)
            echo "ERROR: Unknown argument: $1"
            echo "       Usage: ./bintxt.sh [-f path/to/config.yaml] [--exclude file1 file2 ...]"
            read -rsp $'\nPress any key to exit...' -n 1; echo ""
            exit 1
            ;;
    esac
done

# ── Python resolver ───────────────────────────────────────────────────────────
# Tries .exe-suffixed names first (Git Bash on Windows finds these reliably),
# then falls back to bare names. Skips anything resolving through WindowsApps.
PY_CMD=()
if command -v py.exe >/dev/null 2>&1; then
    PY_CMD=(py.exe -3)
elif command -v python.exe >/dev/null 2>&1; then
    PY_PATH="$(command -v python.exe)"
    if [[ "$PY_PATH" != *WindowsApps* ]]; then
        PY_CMD=(python.exe)
    fi
elif command -v python3.exe >/dev/null 2>&1; then
    PY_PATH="$(command -v python3.exe)"
    if [[ "$PY_PATH" != *WindowsApps* ]]; then
        PY_CMD=(python3.exe)
    fi
elif command -v python >/dev/null 2>&1; then
    PY_PATH="$(command -v python)"
    if [[ "$PY_PATH" != *WindowsApps* ]]; then
        PY_CMD=(python)
    fi
elif command -v python3 >/dev/null 2>&1; then
    PY_PATH="$(command -v python3)"
    if [[ "$PY_PATH" != *WindowsApps* ]]; then
        PY_CMD=(python3)
    fi
fi

if [[ ${#PY_CMD[@]} -eq 0 ]]; then
    echo "ERROR: No usable Python interpreter found."
    echo "       On Windows, install Python and/or use the py launcher."
    echo "       Refusing to use WindowsApps python alias."
    read -rsp $'\nPress any key to exit...' -n 1; echo ""
    exit 1
fi

echo "Using Python: ${PY_CMD[*]}"
"${PY_CMD[@]}" -c "import sys; print('  exe:', sys.executable); print('  ver:', sys.version.split()[0])"

# ── Pre-flight ────────────────────────────────────────────────────────────────
if [[ ! -f "$CFG_FILE" ]]; then
    echo "ERROR: bintxt_cfg.yaml not found."
    echo "       Expected: $CFG_FILE"
    echo "       Copy the template bintxt_cfg.yaml next to bintxt.sh."
    read -rsp $'\nPress any key to exit...' -n 1; echo ""
    exit 1
fi

# ── Pipeline ──────────────────────────────────────────────────────────────────
"${PY_CMD[@]}" "$SCRIPT_DIR/core/pipeline.py" \
    "$SCRIPT_DIR" "$CFG_FILE" "${EXCLUDE_ARGS[@]+"${EXCLUDE_ARGS[@]}"}"

EXIT_CODE=$?
echo ""
read -rsp $'Press any key to exit...\n' -n 1
echo ""
exit $EXIT_CODE
