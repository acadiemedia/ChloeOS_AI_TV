#!/usr/bin/env bash
# ChloeOS Stream Launcher for Linux / Mac / WSL PC
set -e
CWD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$CWD"

echo "=== ChloeOS Live Streamer (PC Host) ==="
export RTMP_URL="rtmp://stream.livepush.io/live/rtmp_0c6e2581584943ec97e7e1104783d429"

# Loop to auto-restart on network disconnects
while true; do
    echo "[$(date)] Starting broadcast engine..."
    python3 automation/btc_chart_streamer.py
    echo "[$(date)] Stream exited. Reconnecting in 5 seconds..."
    sleep 5
done
