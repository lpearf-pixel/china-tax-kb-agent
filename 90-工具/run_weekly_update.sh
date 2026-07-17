#!/usr/bin/env bash
set -u

VAULT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOLS="$VAULT_ROOT/90-工具"
PYTHON_BIN="${PYTHON_BIN:-python3}"
LOG_DIR="$TOOLS/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/weekly-$(date +%Y-%m-%d).log"

{
  echo "=== TaxKB weekly run $(date '+%Y-%m-%d %H:%M:%S %z') ==="
  cd "$TOOLS"

  echo "[1/4] Check official sources (network failures do not overwrite state)"
  "$PYTHON_BIN" taxkb_update.py --vault "$VAULT_ROOT" || echo "WARN: source watcher returned a non-zero status; review the generated report."

  echo "[2/4] Validate Vault"
  "$PYTHON_BIN" taxkb_validate.py --vault "$VAULT_ROOT" || exit 2

  echo "[3/4] Rebuild legal chunks"
  "$PYTHON_BIN" taxkb_export.py --vault "$VAULT_ROOT" --profile full --output 90-工具/output/chunks.jsonl || exit 3

  echo "[4/4] Run retrieval regression"
  "$PYTHON_BIN" taxkb_eval.py --vault "$VAULT_ROOT" --top-k 5 || exit 4
  echo "=== completed ==="
} >> "$LOG_FILE" 2>&1
