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
.\Start-PackHouse.ps1 -Camera indoor_receiving -Device cuda:0
.\Start-PackHouse.ps1 -EveryNFrames 3
.\Start-PackHouse.ps1 -SkipDocker
.\Start-PackHouse.ps1 -NoShow
```

## Stream URLs (bridge running)

| Use | URL |
|-----|-----|
| Rotating dashboard | http://localhost:8080/dashboard.html |
| Browser (solo) | http://localhost:1984/stream.html?src=second_wash_dipping |
| RTSP | rtsp://127.0.0.1:8554/\<stream\> |
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
