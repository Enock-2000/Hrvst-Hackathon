# Hrvst Hackathon — Pack House Vision

Live pack-house monitoring: **Eufy camera → RTSP → YOLO detection** with real-time bounding boxes.

Includes a Docker bridge for Eufy cameras that **do not support native RTSP** (e.g. T8170 Indoor Cam Pan & Tilt), plus a Python runtime for live object detection.

## One-command start

Clone, configure credentials, then run:

```powershell
git clone https://github.com/Enock-2000/Hrvst-Hackathon.git
cd Hrvst-Hackathon
copy .env.example .env
# edit .env with your Eufy account
.\Start-PackHouse.ps1
```

Or double-click **`Start-PackHouse.bat`**.

This will:

1. Start the Eufy camera bridge (Docker)
2. Wait for the RTSP stream on go2rtc
3. Create a Python environment on first run (if needed)
4. Open a live video window with detection boxes (press **Q** to quit)

Full documentation: **[RUN_GUIDE.md](RUN_GUIDE.md)**

## Truck arrival alerts

When live detection sees `license_plate`, `car`, or `vehicle`, it can send:

`POST /api/v1/receiving/truck-arrivals`

Set these optional variables in `.env`:

```env
ARRIVAL_API_BASE_URL=http://localhost:8000
ARRIVAL_API_BEARER_TOKEN=replace-with-api-token
ARRIVAL_ALERT_COOLDOWN_SEC=30
ARRIVAL_ALERT_TIMEOUT_SEC=5
```

Payload sent by runtime:

```json
{
  "truckPlate": "UNKNOWN",
  "gateCameraId": "entrance",
  "suggestedOrderIds": []
}
```

- `gateCameraId` is always the runtime camera ID that produced the detection.
- `truckPlate` is currently `"UNKNOWN"` until plate OCR text extraction is added.

## Project layout

```
Hrvst-Hackathon/
├── Start-PackHouse.ps1      ← run everything
├── RUN_GUIDE.md
├── docker-compose.yml       ← Eufy → RTSP bridge
├── bridge/                  ← eufyp2pstream (local build)
├── go2rtc-config/
├── packhouse-runtime/       ← YOLO live detection
│   ├── models/              ← packhouse_best.pt (required)
│   ├── config/
│   └── src/
```

## Options

```powershell
.\Start-PackHouse.ps1 -NoShow              # no window; save annotated video
.\Start-PackHouse.ps1 -Device xpu          # Intel GPU inference
.\Start-PackHouse.ps1 -Track               # object tracking IDs
.\Start-PackHouse.ps1 -SkipDocker          # vision only (bridge already running)
```

## Stream URLs (when bridge is running)

| Use | URL |
|-----|-----|
| Browser | http://localhost:1984/stream.html?src=living_room |
| RTSP (YOLO / VLC) | `rtsp://127.0.0.1:8554/living_room` |
| go2rtc dashboard | http://localhost:1984/ |

---

## Camera bridge architecture

```
+---------------------+     +----------------+     +------------+
|  eufy-security-ws   | --> |  eufyp2pstream | --> |  go2rtc    |
|  port 3000 (WS API) |     | tcp 63336 HEVC |     | 1984 / UI  |
|                     |     | tcp 63337 AAC  |     | 8554 RTSP  |
+---------------------+     +----------------+     +------------+
```

* **`eufy-security-ws`** ([bropat/eufy-security-ws](https://github.com/bropat/eufy-security-ws)) — Eufy cloud + P2P, WebSocket API on `:3000`.
* **`eufyp2pstream`** (built from `bridge/`, [oischinger/eufyp2pstream](https://github.com/oischinger/eufyp2pstream)) — raw HEVC/AAC on TCP ports for ffmpeg.
* **`go2rtc`** ([AlexxIT/go2rtc](https://github.com/AlexxIT/go2rtc)) — transcodes to browser-friendly H.264 and publishes RTSP/MSE/WebRTC.

### Manual bridge only

```powershell
docker compose up -d --build
```

Wait ~20 s, then open http://localhost:1984/

### Adding cameras

1. Find `serialNumber` via the WS API or `devices.json`.
2. One `eufyp2pstream` container per camera (separate TCP port range).
3. Add a `streams.<name>:` entry in `go2rtc-config/go2rtc.yaml`.

### Bridge troubleshooting

| Symptom | Fix |
|---------|-----|
| Black MSE video | Wait ~10 s or switch to **WebRTC** |
| `LIVESTREAM Start debounced` | `docker compose restart` (~25 s) |
| `data partitioning is not implemented` | Use `-f hevc` in go2rtc ffmpeg pipeline |
| `exec entrypoint.sh: no such file` | Rebuild — Dockerfile strips Windows CRLF |

## Security

* Credentials only in `.env` (gitignored).
* `eufy-data/persistent.json` contains auth tokens — never commit; rotate Eufy password if leaked.

## Credits

* [bropat/eufy-security-ws](https://github.com/bropat/eufy-security-ws)
* [oischinger/eufyp2pstream](https://github.com/oischinger/eufyp2pstream)
* [AlexxIT/go2rtc](https://github.com/AlexxIT/go2rtc)
