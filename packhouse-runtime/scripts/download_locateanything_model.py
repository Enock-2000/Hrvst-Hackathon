#!/usr/bin/env python3
"""Download nvidia/LocateAnything-3B into packhouse-runtime/models/LocateAnything-3B."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = RUNTIME_ROOT / "models" / "LocateAnything-3B"
REPO_ID = "nvidia/LocateAnything-3B"


def main() -> int:
    p = argparse.ArgumentParser(description="Download LocateAnything-3B weights for offline use.")
    p.add_argument("--output", type=Path, default=DEFAULT_OUT, help="Local directory for weights")
    p.add_argument("--repo", default=REPO_ID, help="Hugging Face repo id")
    args = p.parse_args()

    out: Path = args.output.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    marker = out / "config.json"
    if marker.is_file():
        print(f"Model already present at {out}")
        print("Delete the folder to re-download.")
        return 0

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("Install dependencies first: .\\scripts\\Install.ps1", file=sys.stderr)
        return 1

    print(f"Downloading {args.repo} (~7.6 GB) to:\n  {out}\n")
    snapshot_download(repo_id=args.repo, local_dir=str(out))
    print(f"\nDone. Weights saved under:\n  {out}")
    print("\nCopy the whole Hrvst-Hackathon folder to your NVIDIA GPU PC.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
