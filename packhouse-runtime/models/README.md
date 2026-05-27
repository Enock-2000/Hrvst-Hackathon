# Deployment models

| File | Used by default | Purpose |
|------|-----------------|--------|
| `packhouse_best.pt` | **Yes** | Main pack-house detector (19 classes) |
| `plate_best.pt` | No | Reserved for license-plate–focused runs |
| `scale_display.pt` | No | Reserved for scale/display region runs |

Live inference uses `packhouse_best.pt` unless you pass `--model` to `Start-PackHouse.ps1`.
