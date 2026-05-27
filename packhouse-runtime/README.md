# Pack House Runtime (deployment)

YOLO live detection on the Eufy RTSP stream.

**Do not run this folder alone on first setup** — use the repo root:

```powershell
cd ..
.\Start-PackHouse.ps1
```

## Layout

```
packhouse-runtime/
├── models/packhouse_best.pt   # required
├── config/cameras.yaml        # RTSP URL
├── config/class_names.yaml    # readable labels on boxes
├── src/live_inference.py
└── requirements.txt
```

## Advanced (bridge already running)

```powershell
.\.venv\Scripts\Activate.ps1
python src\live_inference.py --show --device cpu
```

See [../RUN_GUIDE.md](../RUN_GUIDE.md).
