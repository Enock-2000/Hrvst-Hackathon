# Pack House — Deployment Run Guide

This repository is configured for **production-style deployment only**: live camera + object detection. Training datasets and scripts have been removed from this tree.

---

## Quick start (one command)

```powershell
cd Hrvst-Hackathon
.\Start-PackHouse.ps1
```

| Step | What happens |
|------|----------------|
| 1 | `docker compose up` in repo root |
| 2 | Waits for go2rtc on port 1984 |
| 3 | Creates `packhouse-runtime/.venv` on first run |
| 4 | Opens live YOLO view with bounding boxes |

Press **Q** in the video window to stop.

---

## First-time prerequisites

### 1. Software

- **Docker Desktop** (running)
- **Python 3.10+** on PATH
- **PowerShell** (or use `Start-PackHouse.bat`)

### 2. Eufy credentials

```powershell
copy .env.example .env
notepad .env
```

Set:

- `EUFY_USERNAME`
- `EUFY_PASSWORD`
- `EUFY_COUNTRY` (e.g. `ZM`, `US`)

Never commit `.env` or the `eufy-data/` folder.

### 3. Model weights

Required file (included in deployment):

```
packhouse-runtime/models/packhouse_best.pt
```

Optional (not used by default):

- `plate_best.pt`
- `scale_display.pt`

---

## Architecture

```
Eufy camera
    → Docker stack (repo root)
        eufy-security-ws → eufyp2pstream → go2rtc
    → RTSP rtsp://127.0.0.1:8554/first_drying_stage
    → packhouse-runtime (YOLO)
    → Live window / saved video
```

---

## Start script options

```powershell
.\Start-PackHouse.ps1 [options]
```

| Option | Description |
|--------|-------------|
| *(none)* | Docker + live window with boxes |
| `-NoShow` | No window; saves annotated video to `packhouse-runtime/runs/live/` |
| `-Device cpu` | CPU inference (default) |
| `-Device xpu` | Intel Arc / XPU (needs `torch+xpu` in venv) |
| `-Device 0` | NVIDIA CUDA GPU |
| `-Track` | ByteTrack — stable object IDs |
| `-Conf 0.25` | Lower confidence threshold |
| `-Model packhouse_best.pt` | Model file under `models/` |
| `-SkipDocker` | Only run vision (bridge already up) |

**Examples:**

```powershell
.\Start-PackHouse.ps1 -NoShow
.\Start-PackHouse.ps1 -Device xpu -Track
.\Start-PackHouse.ps1 -SkipDocker
```

---

## Manual steps (if you prefer)

### Camera only

```powershell
docker compose up -d
```

Verify: http://localhost:8080/dashboard.html (rotating) or http://localhost:1984/stream.html?src=second_wash_dipping

### Vision only (bridge already running)

```powershell
cd packhouse-runtime
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python src\live_inference.py --show
```

---

## Detection classes

Labels on screen use readable names from `packhouse-runtime/config/class_names.yaml`.

| ID | Label | Category |
|----|-------|----------|
| 0 | produce_crate | Logistics |
| 1 | fruit_vegetable | Produce |
| 2 | fresh_produce | Quality |
| 3 | rotten_produce | Quality |
| 4 | license_plate | Delivery |
| 5 | worker | Safety |
| 6 | ppe | Safety |
| 7 | no_ppe | Safety |
| 8–18 | fresh_apple, rotten_banana, … | Produce types |

---

## Ports and URLs

| Port | Service |
|------|---------|
| 3000 | Eufy WebSocket API (control) |
| 1984 | go2rtc web UI + snapshots |
| 8080 | Pack House rotating camera dashboard |
| 8090 | P2P livestream coordinator (mutex) |
| 8554 | **RTSP** (used by YOLO) |
| 8555 | WebRTC |

| URL | Purpose |
|-----|---------|
| http://localhost:8080/dashboard.html | **Recommended** — one camera at a time (carousel) |
| http://localhost:1984/stream.html?src=first_drying_stage | Solo first drying stage view |
| http://localhost:1984/stream.html?src=sorting_1 | Solo sorting 1 view |
| http://localhost:1984/stream.html?src=indoor_receiving | Solo indoor receiving view |
| http://localhost:1984/stream.html?src=second_wash_dipping | Solo second wash & dipping view |
| http://localhost:1984/stream.html?src=outdoor_receiving | Solo outdoor receiving view |
| http://localhost:1984/stream.html?src=drying_dispatch | Solo drying dispatch view |
| http://localhost:1984/stream.html?src=entrance | Solo entrance view |
| http://localhost:8090/status | Which camera holds the P2P slot |
| `rtsp://127.0.0.1:8554/<stream>` | VLC / YOLO — see `packhouse-runtime/config/cameras.yaml` (7 cameras) |

Camera RTSP URL is configured in `packhouse-runtime/config/cameras.yaml`.

### Multi-camera limitation (HomeBase)

All T8170 cameras on one HomeBase share **one** Eufy P2P livestream slot ([eufy-security-ws #15](https://github.com/bropat/eufy-security-ws/issues/15)). Opening go2rtc’s 4-up grid starts four ffmpeg probes at once; only one camera receives HEVC — others show `Could not find codec parameters`.

This repo uses:

- **`stream-coordinator`** — mutex so bridges take turns on `start_livestream`
- **`packhouse-dashboard`** — browser carousel (one active player)

---

## Outputs

| Mode | Output |
|------|--------|
| Default (`-show`) | On-screen boxes + console log every 30 frames |
| `-NoShow` | `packhouse-runtime/runs/live/<camera>_<timestamp>/` (annotated video) |

---

## Troubleshooting

### Docker / camera

| Problem | Fix |
|---------|-----|
| Docker not running | Start Docker Desktop |
| Missing `.env` | Create from `.env.example` |
| `eufyp2pstream` restarting | `docker compose up -d --build` |
| Black video in browser | Wait 20 s; try WebRTC; `docker compose restart go2rtc` |
| No RTSP | `docker compose restart go2rtc` |

### Vision

| Problem | Fix |
|---------|-----|
| Model not found | Ensure `packhouse-runtime/models/packhouse_best.pt` exists |
| Stream error | Start bridge first; test RTSP in VLC |
| Slow on CPU | `-Device xpu` or `-Device 0`; or lower load with manual `--imgsz 480` |
| No detections | `-Conf 0.25`; point camera at crates / produce / people |
| First run slow | pip installs dependencies into `.venv` (one-time) |

### Stop

- **Q** in video window, or **Ctrl+C** in terminal
- Stop Docker: `docker compose down`

---

## Security

- Do not commit `.env` or `eufy-data/`
- Rotate Eufy password if `eufy-data/persistent.json` is exposed

---

## Folder reference

| Path | Role |
|------|------|
| `Start-PackHouse.ps1` | **Main entry point** |
| `docker-compose.yml`, `bridge/`, `go2rtc-config/` | Eufy → RTSP Docker stack |
| `packhouse-runtime/` | YOLO inference app |
| `packhouse-runtime/models/` | `.pt` weight files |
| `packhouse-runtime/config/cameras.yaml` | RTSP URLs |
| `packhouse-runtime/config/class_names.yaml` | Display labels |

---

## Future work (not in this deployment)

- Zone-based inventory and database logging
- License plate OCR and scale OCR
- Simultaneous multi-P2P (blocked by Eufy HomeBase; use carousel dashboard)
- Web dashboard with YOLO overlays

Training is done offline; deploy only the `models/*.pt` files produced from training.
