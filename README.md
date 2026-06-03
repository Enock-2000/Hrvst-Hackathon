# Hrvst Hackathon — Pack House Vision

Live pack-house monitoring: **Eufy cameras → go2rtc → NVIDIA [LocateAnything-3B](https://huggingface.co/nvidia/LocateAnything-3B)** (car / truck detection, CUDA).

Includes a Docker bridge for Eufy cameras without native RTSP, a **stream coordinator** (one HomeBase P2P stream at a time), and a rotating **dashboard** at http://localhost:8080/dashboard.html.

## One-command start (NVIDIA GPU PC)

```powershell
git clone https://github.com/Enock-2000/Hrvst-Hackathon.git
cd Hrvst-Hackathon
copy .env.example .env
# edit .env with Eufy credentials

cd packhouse-runtime
.\scripts\Install.ps1
.\scripts\Download-LocateAnythingModel.ps1   # ~7.6 GB, once

cd ..
.\Start-PackHouse.ps1
```

Or double-click **`Start-PackHouse.bat`**.

Full documentation: **[RUN_GUIDE.md](RUN_GUIDE.md)**

## Cameras

| Camera ID | go2rtc stream |
|-----------|----------------|
| `first_drying_stage` | first_drying_stage |
| `sorting_1` | sorting_1 |
| `indoor_receiving` | indoor_receiving |
| `second_wash_dipping` | second_wash_dipping (default) |

```powershell
.\Start-PackHouse.ps1 -Camera sorting_1
```

**Note:** Eufy HomeBase allows **one P2P livestream at a time**. Use the [rotating dashboard](http://localhost:8080/dashboard.html) or solo stream URLs — not a 4-up go2rtc grid on one HomeBase.

## Transfer workflow

1. Run `Download-LocateAnythingModel.ps1` on any PC with internet (~7.3 GB → `packhouse-runtime/models/LocateAnything-3B/`).
2. Copy the whole repo (including `models/LocateAnything-3B/`) to a machine with an **NVIDIA GPU**.
3. `Install.ps1` + `Start-PackHouse.ps1` on the GPU PC.

## Options

```powershell
.\Start-PackHouse.ps1 -NoShow              # no window; save annotated video
.\Start-PackHouse.ps1 -Camera first_drying_stage     # YOLO on first drying stage
.\Start-PackHouse.ps1 -Camera sorting_1              # YOLO on sorting 1 camera
.\Start-PackHouse.ps1 -Camera indoor_receiving        # YOLO on indoor receiving
.\Start-PackHouse.ps1 -Camera second_wash_dipping     # YOLO on second wash & dipping
.\Start-PackHouse.ps1 -Camera outdoor_receiving       # YOLO on outdoor receiving
.\Start-PackHouse.ps1 -Camera drying_dispatch         # YOLO on drying dispatch
.\Start-PackHouse.ps1 -Camera entrance                # YOLO on entrance
.\Start-PackHouse.ps1 -Device xpu          # Intel GPU inference
.\Start-PackHouse.ps1 -Track               # object tracking IDs
.\Start-PackHouse.ps1 -SkipDocker          # vision only (bridge already running)
```

## Stream URLs (bridge running)

| Use | URL |
|-----|-----|
| **Pack House dashboard** (rotating) | http://localhost:8080/dashboard.html |
| Browser (first drying stage) | http://localhost:1984/stream.html?src=first_drying_stage |
| Browser (sorting 1) | http://localhost:1984/stream.html?src=sorting_1 |
| Browser (indoor receiving) | http://localhost:1984/stream.html?src=indoor_receiving |
| Browser (second wash & dipping) | http://localhost:1984/stream.html?src=second_wash_dipping |
| Browser (outdoor receiving) | http://localhost:1984/stream.html?src=outdoor_receiving |
| Browser (drying dispatch) | http://localhost:1984/stream.html?src=drying_dispatch |
| Browser (entrance) | http://localhost:1984/stream.html?src=entrance |
| RTSP (YOLO / VLC) | `rtsp://127.0.0.1:8554/<stream>` — all 7 camera stream IDs in `packhouse-runtime/config/cameras.yaml` |
| go2rtc stream list | http://localhost:1984/ |
| Coordinator status | http://localhost:8090/status |
| go2rtc | http://localhost:1984/ |

## Truck arrival alerts

Optional `.env` variables: `ARRIVAL_API_BASE_URL`, `ARRIVAL_API_BEARER_TOKEN` — posts when **car** or **truck** is detected.

## Layout

```
Hrvst-Hackathon/
├── Start-PackHouse.ps1
├── docker-compose.yml       # eufy-security-ws, coordinator, 4× bridge, go2rtc, dashboard
├── bridge/                  # eufyp2pstream + stream_coordinator
├── go2rtc-config/
└── packhouse-runtime/
    ├── models/LocateAnything-3B/   # downloaded weights (gitignored)
    ├── config/locateanything.yaml
    └── src/live_inference.py
```

## Credits

- [bropat/eufy-security-ws](https://github.com/bropat/eufy-security-ws)
- [oischinger/eufyp2pstream](https://github.com/oischinger/eufyp2pstream)
- [AlexxIT/go2rtc](https://github.com/AlexxIT/go2rtc)
- [nvidia/LocateAnything-3B](https://huggingface.co/nvidia/LocateAnything-3B)
