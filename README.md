# Eufy Bridge (Hrvst Hackathon)

A small docker-based bridge that exposes Eufy cameras as RTSP / HLS / WebRTC
streams via [`bropat/eufy-security-ws`](https://github.com/bropat/eufy-security-ws),
[`oischinger/eufyp2pstream`](https://github.com/oischinger/eufyp2pstream), and
[`go2rtc`](https://github.com/AlexxIT/go2rtc).

## Architecture

```
+----------------------+     +------------------+     +----------+
| eufy-security-ws     | --> | eufyp2pstream    | --> | go2rtc   |
| (port 3000, WS API)  |     | (RTSP :8554)     |     | (:1984)  |
+----------------------+     +------------------+     +----------+
        |
        v
    Eufy Cloud
```

* `eufy-security-ws` — talks to the Eufy cloud / station, exposes a WebSocket API.
* `eufyp2pstream`   — pulls the camera P2P stream and republishes it over RTSP.
* `go2rtc`          — fans the RTSP stream out to HLS / WebRTC / MSE for browsers.

## Repo contents

| File / dir                | Purpose                                         |
| ------------------------- | ----------------------------------------------- |
| `go2rtc-config/go2rtc.yaml` | go2rtc stream definitions                     |
| `devices.json`            | Sample `state` response from `eufy-security-ws` |
| `.gitignore`              | Excludes credentials, tokens and runtime data   |

> `docker-compose.yml`, `docker-compose.yml.backup`, `eufy-data/` and
> `stream-test.json` are intentionally **gitignored** because they contain
> Eufy account credentials, auth/refresh tokens and private keys.

## Quick start

1. Copy the example compose file and fill in your Eufy credentials:

   ```bash
   cp docker-compose.example.yml docker-compose.yml
   # edit USERNAME / PASSWORD / COUNTRY
   ```

2. Bring the stack up:

   ```bash
   docker compose up -d
   ```

3. Open go2rtc at <http://localhost:1984> and play the `living_room` stream.

## Example `docker-compose.yml`

```yaml
services:
  eufy-security-ws:
    image: bropat/eufy-security-ws:latest
    container_name: eufy-security-ws
    restart: unless-stopped
    ports:
      - "3000:3000"
    environment:
      - USERNAME=${EUFY_USERNAME}
      - PASSWORD=${EUFY_PASSWORD}
      - COUNTRY=${EUFY_COUNTRY:-US}
      - TRUSTED_DEVICE_NAME=eufyBridge
      - WS_LISTEN_PORT=3000
    volumes:
      - ./eufy-data:/data

  eufyp2pstream:
    image: oischinger/eufyp2pstream:latest
    container_name: eufyp2pstream
    restart: unless-stopped
    ports:
      - "8000:8000"
      - "8554:8554"
    environment:
      - WS_URL=ws://eufy-security-ws:3000
    depends_on:
      - eufy-security-ws

  go2rtc:
    image: alexxit/go2rtc:latest
    container_name: go2rtc
    restart: unless-stopped
    ports:
      - "1984:1984"
    volumes:
      - ./go2rtc-config:/config
    depends_on:
      - eufyp2pstream
```

Put your secrets in a local `.env` file (also gitignored):

```env
EUFY_USERNAME=you@example.com
EUFY_PASSWORD=changeme
EUFY_COUNTRY=US
```
