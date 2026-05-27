# Standalone (non-Home-Assistant) build of oischinger/eufyp2pstream.
# Bridges eufy-security-ws WebSocket P2P streams to plain TCP sockets
# so go2rtc (via exec:ffmpeg) can consume them as RTSP/MSE/WebRTC.

FROM python:3.12-alpine

RUN apk add --no-cache --virtual .build-deps build-base \
 && pip install --no-cache-dir aiohttp \
 && apk del --no-cache --purge .build-deps

WORKDIR /app
COPY eufyp2pstream.py websocket.py entrypoint.sh /app/

# Replace the hard-coded HA addon hostname with the EUFY_WS_HOST env var
# (script imports `os` already, so this is safe).
RUN sed -i 's/\r$//' /app/entrypoint.sh \
 && sed -i 's|"402f1039-eufy-security-ws"|os.environ.get("EUFY_WS_HOST","eufy-security-ws")|' /app/eufyp2pstream.py \
 && chmod +x /app/entrypoint.sh

EXPOSE 63336 63337 63338

ENV EUFY_WS_HOST=eufy-security-ws \
    EUFY_WS_PORT=3000 \
    PYTHONUNBUFFERED=1

ENTRYPOINT ["/app/entrypoint.sh"]
