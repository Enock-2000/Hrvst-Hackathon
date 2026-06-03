# Model weights

| Path | Size | Purpose |
|------|------|---------|
| `LocateAnything-3B/` | ~7.6 GB | [nvidia/LocateAnything-3B](https://huggingface.co/nvidia/LocateAnything-3B) |

## Download (on any PC with internet)

```powershell
cd packhouse-runtime
.\scripts\Download-LocateAnythingModel.ps1
```

Copy the entire `Hrvst-Hackathon` folder (including `models/LocateAnything-3B/`) to a machine with an **NVIDIA GPU** and CUDA PyTorch.

This directory is gitignored — do not commit weights.
