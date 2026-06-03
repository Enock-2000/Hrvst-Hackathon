#!/usr/bin/env python3
"""Verify LocateAnything install (imports, CUDA, optional one-image smoke test)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RUNTIME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RUNTIME / "src"))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--smoke",
        action="store_true",
        help="Run one detection on a synthetic image (requires CUDA; slow on CPU)",
    )
    p.add_argument(
        "--allow-cpu",
        action="store_true",
        help="Allow smoke test without CUDA (very slow, may OOM)",
    )
    args = p.parse_args()

    print("=== LocateAnything install check ===\n")

    try:
        import torch

        print(f"  torch: {torch.__version__}")
        print(f"  cuda:  {torch.cuda.is_available()}", end="")
        if torch.cuda.is_available():
            print(f" ({torch.cuda.get_device_name(0)})")
        else:
            print()
    except ImportError as e:
        print(f"  FAIL torch: {e}")
        return 1

    for pkg in ("transformers", "PIL", "cv2", "yaml", "huggingface_hub"):
        try:
            __import__(pkg if pkg != "PIL" else "PIL")
            print(f"  {pkg}: ok")
        except ImportError as e:
            print(f"  FAIL {pkg}: {e}")
            return 1

    from detectors.locateanything_parse import detections_from_answer

    sample = "<ref>car</ref><box><100><200><400><500></box>"
    boxes = detections_from_answer(sample, 640, 480, ["car", "truck"])
    print(f"  parse smoke: {len(boxes)} box(es), label={boxes[0].label if boxes else 'n/a'}")

    local_cfg = RUNTIME / "models" / "LocateAnything-3B" / "config.json"
    if local_cfg.is_file():
        print(f"  local weights: {local_cfg.parent}")
    else:
        print("  local weights: not downloaded — run .\\scripts\\Download-LocateAnythingModel.ps1")

    if not args.smoke:
        print("\n  Install check OK.")
        if not torch.cuda.is_available():
            print("  No CUDA on this PC — download weights here, run Start-PackHouse on NVIDIA GPU.")
        return 0

    if not torch.cuda.is_available() and not args.allow_cpu:
        print("\n  SKIP model smoke: no CUDA. Re-run with --smoke --allow-cpu to try CPU anyway.")
        return 0

    import numpy as np
    from detectors.locateanything_backend import load_locateanything_config
    from detectors.locateanything_worker import LocateAnythingWorker

    cfg = load_locateanything_config(RUNTIME / "config" / "locateanything.yaml")
    cfg["resize_short_side"] = 512
    cfg["max_new_tokens"] = 512
    cfg["verbose_generate"] = False
    model_id = str(cfg.get("model_id", "nvidia/LocateAnything-3B"))

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if device.startswith("cuda") else torch.float32
    print(f"\n  Loading {model_id} on {device} (first run downloads ~7.6 GB)...")

    worker = LocateAnythingWorker(model_id, device=device, dtype=dtype)
    from PIL import Image

    img = Image.fromarray(np.zeros((480, 640, 3), dtype=np.uint8))
    result = worker.detect(img, ["car", "truck"], generation_mode="hybrid", max_new_tokens=512, verbose=False)
    answer = str(result.get("answer", ""))[:200]
    print(f"  model answer (truncated): {answer!r}")
    print("\n  Smoke test OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
