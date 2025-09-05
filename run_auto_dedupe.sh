set -euo pipefail

source ./config.env

mkdir -p "$LOG_DIR"

# If no files in INPUT, exit quietly (journal note only)
if ! find "$INPUT" -type f -print -quit | grep -q . ; then
  echo "$(date -Is) auto_dedupe: SKIP — no files under $INPUT. (Log=$LOG_FILE)"
  exit 0
fi

# prevent overlapping runs
exec 9>"$LOCKFILE"
if ! flock -n 9; then
  echo "$(date -Is) auto_dedupe: another run is already in progress (lock: $LOCKFILE)."
  exit 1
fi

ln -sf "$LOG_FILE" "$LOG_DIR/latest.log"
echo "$(date -Is) auto_dedupe: START live. Input=$INPUT Output=$OUTPUT Log=$LOG_FILE"

set +e
"$VENV_PY" "$SCRIPT" \
  --input-dir "$INPUT" \
  --output-dir "$OUTPUT" \
  --log-file "$LOG_FILE"
RC=$?
set -e

echo "$(date -Is) auto_dedupe: END live. ExitCode=$RC Log=$LOG_FILE"
exit "$RC"
