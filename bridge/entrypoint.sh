#!/bin/sh
set -e
echo "[eufyp2pstream] connecting to ws://${EUFY_WS_HOST}:${EUFY_WS_PORT}"
exec python3 -u /app/eufyp2pstream.py "${EUFY_WS_PORT}"
