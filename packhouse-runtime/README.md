# Pack House Runtime

Live **car / truck** detection with **NVIDIA LocateAnything-3B** on Eufy RTSP streams (CUDA required at runtime).

## Quick start

```powershell
# 1. Dependencies (Python 3.12 + CUDA PyTorch)
.\scripts\Install.ps1

# 2. Download model (~7.6 GB) — can run on any PC, then copy project to GPU machine
.\scripts\Download-LocateAnythingModel.ps1

# 3. From repo root (NVIDIA GPU + Docker for cameras)
cd ..
.\Start-PackHouse.ps1
```

## Layout

```
packhouse-runtime/
├── config/
│   ├── cameras.yaml          # RTSP / go2rtc sources
│   └── locateanything.yaml   # model path, categories, speed
├── models/LocateAnything-3B/ # downloaded weights (gitignored)
├── src/
│   ├── live_inference.py
│   └── detectors/
├── scripts/
│   ├── Install.ps1
│   ├── Download-LocateAnythingModel.ps1
│   └── test_locateanything_install.py
└── requirements.txt
```

## Manual inference

```powershell
.\.venv\Scripts\Activate.ps1
python src\live_inference.py --device cuda:0 --show --camera entrance
```

## Transfer to NVIDIA PC

1. Run `Download-LocateAnythingModel.ps1` on a machine with good internet.
2. Copy the full `Hrvst-Hackathon` folder (include `models/LocateAnything-3B/`).
3. On the GPU PC: `.\scripts\Install.ps1` then `.\Start-PackHouse.ps1`.
