#!/bin/bash
# =============================================================================
# AIFred Railway Entrypoint
# Starts the health HTTP server FIRST (Railway needs it fast), then trading loop.
# =============================================================================

set -e

MODE=${TRADING_MODE:-paper}
DRY_RUN_FLAG=""
if [ "$DRY_RUN" = "true" ]; then
    DRY_RUN_FLAG="--dry-run"
fi

echo "[start.sh] Starting AIFred Trading Engine on Railway"

# Download trained model checkpoints from GitHub if not present
CKPT_DIR="/app/checkpoints/technical"
if [ ! -f "$CKPT_DIR/lstm_latest.pt" ]; then
    echo "[start.sh] Downloading trained model checkpoints..."
    mkdir -p "$CKPT_DIR"
    REPO_BASE="https://raw.githubusercontent.com/Yazidryuichi/aifred-trading/main/python/checkpoints/technical"
    curl -sL "$REPO_BASE/lstm_latest.pt" -o "$CKPT_DIR/lstm_latest.pt" && echo "[start.sh] LSTM checkpoint downloaded"
    curl -sL "$REPO_BASE/transformer_latest.pt" -o "$CKPT_DIR/transformer_latest.pt" && echo "[start.sh] Transformer checkpoint downloaded"
    curl -sL "$REPO_BASE/cnn_latest.pt" -o "$CKPT_DIR/cnn_latest.pt" && echo "[start.sh] CNN checkpoint downloaded"
    ls -la "$CKPT_DIR/"
else
    echo "[start.sh] Model checkpoints already present"
fi
echo "[start.sh] PORT=${PORT:-8080}"
echo "[start.sh] mode=$MODE, dry_run=$DRY_RUN"
echo "[start.sh] Contents of /app/src/:"
ls -la /app/src/ 2>&1
echo "[start.sh] src/data exists?"
ls -la /app/src/data/ 2>&1 || echo "[start.sh] src/data/ MISSING!"

# Start the health/status HTTP server FIRST — it's lightweight and starts in <2s
python health_server.py &
HEALTH_PID=$!
echo "[start.sh] Health server started (PID=$HEALTH_PID)"

# Wait for health server to bind before starting heavy trading loop
sleep 3

# Start the trading engine with mode, portfolio value, and dry-run flags
python -m src.main --mode "$MODE" --portfolio-value 5.50 $DRY_RUN_FLAG &
TRADING_PID=$!
echo "[start.sh] Trading engine started (PID=$TRADING_PID, mode=$MODE)"

# Wait for either process to exit; if one dies, kill the other
wait -n $HEALTH_PID $TRADING_PID
EXIT_CODE=$?
echo "[start.sh] A process exited with code $EXIT_CODE, shutting down..."

kill $HEALTH_PID $TRADING_PID 2>/dev/null || true
wait
exit $EXIT_CODE
