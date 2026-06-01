# Pack House — Deployment Run Guide

Eufy multi-camera bridge + **NVIDIA LocateAnything-3B** (CUDA).

---

## Quick start

```powershell
cd Hrvst-Hackathon
copy .env.example .env

cd packhouse-runtime
.\scripts\Install.ps1
.\scripts\Download-LocateAnythingModel.ps1

cd ..
.\Start-PackHouse.ps1 -Camera second_wash_dipping
```

---

## Prerequisites

- Docker Desktop
- Python **3.12** + **NVIDIA CUDA** for inference
- `packhouse-runtime/models/LocateAnything-3B/` (~7.6 GB, gitignored)
- Eufy credentials in `.env`

---

## Architecture

```
Eufy cameras (4× T8170)
  → eufy-security-ws
  → stream-coordinator (one P2P lease at a time)
  → eufyp2pstream_<camera> (HEVC on TCP)
  → go2rtc (H.264 RTSP)
  → LocateAnything-3B (CUDA)
  → live window / API alerts
```

Rotating viewer: **http://localhost:8080/dashboard.html**

---

## Cameras

Configured in `packhouse-runtime/config/cameras.yaml`:

- `first_drying_stage`
- `sorting_1`
- `indoor_receiving`
- `second_wash_dipping` (default)

Detection categories in `packhouse-runtime/config/locateanything.yaml` (`car`, `truck`).

---

## Start script

| Option | Description |
|--------|-------------|
| `-Camera <id>` | Camera from `cameras.yaml` |
| `-Device cuda:0` | NVIDIA GPU |
| `-EveryNFrames 3` | Run model every N frames |
| `-SkipDocker` | Inference only |
| `-NoShow` | Headless |

---

## Adding a camera

1. Serial in `devices.json` / Eufy app.
2. Duplicate an `eufyp2pstream_*` service in `docker-compose.yml` (unique ports + `EUFY_STREAM_NAME`).
3. Add stream in `go2rtc-config/go2rtc.yaml`.
4. Add entry in `packhouse-runtime/config/cameras.yaml`.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| No frames | One stream at a time — use dashboard or wait for coordinator lease |
| Model not found | `Download-LocateAnythingModel.ps1` |
| CUDA required | Run inference on NVIDIA PC |
| `eufy-security-ws` down | Check `.env`, `docker logs eufy-security-ws` |
| RTSP 404 | Bridge not healthy — check `docker logs eufyp2pstream_<name>` |

---

## Security

- Never commit `.env` or `eufy-data/`.
- Model weights are local only (`models/LocateAnything-3B/`).
