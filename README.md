# Eufy Bridge (Hrvst Hackathon)

A docker-based bridge that exposes Eufy cameras (including models that
**do not support native RTSP**, like the T8170 Indoor Cam Pan & Tilt) as
RTSP / HLS / MSE / WebRTC streams that any browser, VLC, Frigate or
Home Assistant can consume.

## Architecture

```
+---------------------+     +----------------+     +------------+
|  eufy-security-ws   | --> |  eufyp2pstream | --> |  go2rtc    |
|  bropat/...:latest  |     |  (local build) |     | alexxit/...|
|  port 3000 (WS API) |     | tcp 63336 HEVC |     | 1984 / UI  |
|                     |     | tcp 63337 AAC  |     | 8554 RTSP  |
|                     |     |                |     | 8555 WebRTC|
+---------------------+     +----------------+     +------------+
         ^                                                ^
         |                                                |
   ws to Eufy Cloud                              your browser / VLC
   + P2P to Camera
```

* **`eufy-security-ws`** ([bropat/eufy-security-ws](https://github.com/bropat/eufy-security-ws))
  — talks to the Eufy cloud and your station/cameras, exposes a
  WebSocket JSON-RPC API on `:3000`.
* **`eufyp2pstream`** (built locally from `bridge/`, source from
  [oischinger/eufyp2pstream](https://github.com/oischinger/eufyp2pstream))
  — connects to `eufy-security-ws`, calls `device.start_livestream`
  whenever something connects to its TCP ports, then proxies the raw
  H.264/H.265 video bytes on `:63336` and G.711 audio on `:63337`.
  We build it locally because the project is distributed as a Home
  Assistant addon — there is no `oischinger/eufyp2pstream` image on
  Docker Hub.
* **`go2rtc`** ([AlexxIT/go2rtc](https://github.com/AlexxIT/go2rtc))
  — runs `ffmpeg` to read the HEVC bytes from `eufyp2pstream`,
  transcodes to H.264 Main / `yuv420p` so browser MSE/WebRTC works,
  and republishes the stream as RTSP/MSE/HLS/WebRTC.

## Repo layout

| Path                       | Purpose                                          |
| -------------------------- | ------------------------------------------------ |
| `docker-compose.yml`       | The three-service stack (uses `${EUFY_*}` env)   |
| `.env.example`             | Template for the Eufy credentials                |
| `bridge/Dockerfile`        | Builds the P2P → TCP sidecar                     |
| `bridge/eufyp2pstream.py`  | Upstream P2P bridge script                       |
| `bridge/websocket.py`      | Upstream WS client used by the script            |
| `bridge/entrypoint.sh`     | Launches the bridge with `EUFY_WS_HOST/PORT`     |
| `go2rtc-config/go2rtc.yaml`| Stream definitions / ffmpeg pipeline             |
| `devices.json`             | Sample `state` response from `eufy-security-ws`  |

Intentionally **not** in git (see `.gitignore`):

* `.env`                       — your real Eufy credentials
* `eufy-data/`                 — `persistent.json` with auth tokens / cloud token / private keys
* `docker-compose.yml.backup`  — old snapshot that contained hard-coded creds
* `stream-test.json`           — multi-MB local capture

## Quick start

1. **Clone & set up credentials**

   ```bash
   git clone https://github.com/Enock-2000/Hrvst-Hackathon.git eufy-bridge
   cd eufy-bridge
   cp .env.example .env
   # edit .env -> EUFY_USERNAME / EUFY_PASSWORD / EUFY_COUNTRY
   ```

2. **Bring the stack up** (builds the local `eufyp2pstream` image on
   first run; ~2 min):

   ```bash
   docker compose up -d --build
   ```

3. **Wait ~20 s** for `eufy-security-ws` to authenticate to the Eufy
   cloud and establish the P2P session, then open the go2rtc UI:

   <http://localhost:1984/>

   Click `living_room` → pick **MSE** or **WebRTC**.

## Stream URLs

For the bundled `living_room` stream (T8170 transcoded to 1080p H.264):

| Consumer                | URL                                                              |
| ----------------------- | ---------------------------------------------------------------- |
| **Browser** (MSE/WebRTC)| <http://localhost:1984/stream.html?src=living_room>              |
| VLC / ffplay / Frigate  | `rtsp://localhost:8554/living_room`                              |
| JPEG snapshot           | <http://localhost:1984/api/frame.jpeg?src=living_room>           |
| go2rtc dashboard        | <http://localhost:1984/>                                         |

## Adding more cameras

1. Find the camera's `serialNumber` via the WS API:

   ```bash
   curl -s http://localhost:3000/  # WS handshake, then use any ws client
   ```

   …or read `devices.json` for the sample response.

2. Add another `device.start_livestream` consumer port to `bridge/`
   (the upstream script only handles one camera at a time — for
   multi-camera setups you currently need one `eufyp2pstream`
   container per camera, each on its own TCP port range).

3. Add a corresponding `streams.<name>:` entry to
   `go2rtc-config/go2rtc.yaml`.

## Troubleshooting

| Symptom                                | Likely cause / fix                                                                                              |
| -------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Browser shows black screen, "MSE" tag  | First load before first IDR — wait ~10 s. If it persists, switch the player to **WebRTC**.                       |
| `LIVESTREAM Start debounced (active=True)` in `eufyp2pstream` logs, 0 frames | Stale P2P session. Run `docker compose restart` (~25 s) to re-auth `eufy-security-ws` and clear state. |
| `data partitioning is not implemented` in ffmpeg logs | The camera is emitting H.265 (HEVC) but ffmpeg was set to `-f h264`. Use the supplied `-f hevc` pipeline. |
| Picture is rotated / sideways          | The T8170 ships frames in the orientation it's mounted in. Add `transpose=1` (CW) or `transpose=2` (CCW) to the `-vf` chain in `go2rtc.yaml`. |
| `pull access denied for oischinger/eufyp2pstream` | The upstream project isn't on Docker Hub. This repo builds it locally via `bridge/Dockerfile` — make sure you ran `docker compose up --build`. |

## Security notes

* Credentials live only in `.env` (gitignored). The committed
  `docker-compose.yml` references them as `${EUFY_USERNAME}` /
  `${EUFY_PASSWORD}`.
* `eufy-data/persistent.json` contains Firebase refresh tokens,
  the Eufy `cloud_token`, your `clientPrivateKey`, and GCM push
  credentials. It is gitignored — if it ever leaks, **rotate your
  Eufy password immediately** to invalidate the derived tokens.

## Credits

* [bropat/eufy-security-ws](https://github.com/bropat/eufy-security-ws)
* [oischinger/eufyp2pstream](https://github.com/oischinger/eufyp2pstream)
* [AlexxIT/go2rtc](https://github.com/AlexxIT/go2rtc)
* [fuatakgun/eufy_security](https://github.com/fuatakgun/eufy_security) — original architecture inspiration
