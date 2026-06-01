from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch
import yaml
from PIL import Image

from detectors.draw import annotate_frame, filter_detections
from detectors.locateanything_parse import detections_from_answer
from detectors.locateanything_worker import LocateAnythingWorker
from detectors.types import FrameDetections

RUNTIME_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LA_CFG = RUNTIME_ROOT / "config" / "locateanything.yaml"
DEFAULT_LOCAL_MODEL = RUNTIME_ROOT / "models" / "LocateAnything-3B"


def resolve_model_location(cfg: dict) -> tuple[str, bool]:
    """Return (path_or_hub_id, is_local_dir)."""
    rel = cfg.get("model_path", "models/LocateAnything-3B")
    local = Path(rel) if Path(rel).is_absolute() else RUNTIME_ROOT / rel
    if local.is_dir() and (local / "config.json").is_file():
        return str(local), True
    return str(cfg.get("model_id", "nvidia/LocateAnything-3B")), False


def load_locateanything_config(path: Path | None = None) -> dict:
    cfg_path = path or DEFAULT_LA_CFG
    if not cfg_path.is_file():
        return {
            "model_id": "nvidia/LocateAnything-3B",
            "categories": ["car", "truck"],
            "generation_mode": "hybrid",
            "max_new_tokens": 2048,
            "temperature": 0.7,
            "default_confidence": 1.0,
            "min_conf": 0.0,
            "min_area_px": 400,
            "resize_short_side": 768,
            "every_n_frames": 1,
            "verbose_generate": False,
        }
    with cfg_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _resize_short_side(image: Image.Image, short_side: int) -> tuple[Image.Image, float]:
    w, h = image.size
    if short_side <= 0 or min(w, h) <= short_side:
        return image, 1.0
    if w <= h:
        scale = short_side / w
        new_w, new_h = short_side, int(h * scale)
    else:
        scale = short_side / h
        new_w, new_h = int(w * scale), short_side
    return image.resize((new_w, new_h), Image.BILINEAR), scale


class LocateAnythingBackend:
    def __init__(self, cfg: dict, device: str = "cuda"):
        if not torch.cuda.is_available():
            raise RuntimeError(
                "LocateAnything backend requires an NVIDIA GPU with CUDA PyTorch."
            )
        self.cfg = cfg
        self.device = device if str(device).startswith("cuda") else "cuda:0"
        self.categories = [str(c) for c in cfg.get("categories", ["car", "truck"])]
        self.generation_mode = str(cfg.get("generation_mode", "hybrid"))
        self.max_new_tokens = int(cfg.get("max_new_tokens", 2048))
        self.temperature = float(cfg.get("temperature", 0.7))
        self.default_confidence = float(cfg.get("default_confidence", 1.0))
        self.min_conf = float(cfg.get("min_conf", 0.0))
        self.min_area_px = int(cfg.get("min_area_px", 400))
        self.resize_short_side = int(cfg.get("resize_short_side", 768))
        self.every_n_frames = max(1, int(cfg.get("every_n_frames", 1)))
        self.verbose_generate = bool(cfg.get("verbose_generate", False))
        self._worker: LocateAnythingWorker | None = None
        self._frame_counter = 0
        self._last: FrameDetections = FrameDetections()
        self._last_ms = 0.0

    def load(self) -> None:
        model_loc, is_local = resolve_model_location(self.cfg)
        if is_local:
            print(f"  Loading LocateAnything from local: {model_loc}")
        else:
            print(f"  Loading LocateAnything from Hugging Face: {model_loc}")
            print("  (Run scripts/Download-LocateAnythingModel.ps1 to cache under models/)")
        t0 = time.time()
        self._worker = LocateAnythingWorker(
            model_loc,
            device=self.device,
            attn_implementation=str(self.cfg.get("attn_implementation", "sdpa")),
        )
        print(f"  LocateAnything ready in {time.time() - t0:.1f}s on {self.device}")

    def describe(self) -> str:
        return (
            f"LocateAnything-3B device={self.device} "
            f"categories={self.categories} mode={self.generation_mode} "
            f"resize={self.resize_short_side} every_n={self.every_n_frames}"
        )

    def predict(self, frame_bgr) -> FrameDetections:
        self._frame_counter += 1
        if self.every_n_frames > 1 and self._frame_counter % self.every_n_frames != 1:
            return self._last

        assert self._worker is not None
        h, w = frame_bgr.shape[:2]
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb)
        scale_back = 1.0
        if self.resize_short_side > 0:
            pil, scale = _resize_short_side(pil, self.resize_short_side)
            scale_back = 1.0 / scale if scale else 1.0

        t0 = time.time()
        result = self._worker.detect(
            pil,
            self.categories,
            generation_mode=self.generation_mode,
            max_new_tokens=self.max_new_tokens,
            temperature=self.temperature,
            verbose=self.verbose_generate,
        )
        self._last_ms = (time.time() - t0) * 1000.0

        answer = str(result.get("answer", ""))
        pw, ph = pil.size
        detections = detections_from_answer(
            answer,
            pw,
            ph,
            self.categories,
            default_confidence=self.default_confidence,
        )

        if scale_back != 1.0:
            for box in detections:
                box.x1 *= scale_back
                box.y1 *= scale_back
                box.x2 *= scale_back
                box.y2 *= scale_back

        # Clamp to original frame size
        for box in detections:
            box.x1 = max(0.0, min(float(w - 1), box.x1))
            box.y1 = max(0.0, min(float(h - 1), box.y1))
            box.x2 = max(0.0, min(float(w - 1), box.x2))
            box.y2 = max(0.0, min(float(h - 1), box.y2))

        filtered = filter_detections(
            FrameDetections(boxes=detections),
            min_conf=self.min_conf,
            min_area_px=self.min_area_px,
        )
        self._last = filtered
        return filtered

    def annotate(self, frame_bgr: np.ndarray, detections: FrameDetections, *, line_width: int = 2):
        return annotate_frame(frame_bgr, detections, line_width=line_width, show_conf=False)

    @property
    def last_inference_ms(self) -> float:
        return self._last_ms

    @staticmethod
    def build_from_args(args) -> "LocateAnythingBackend":
        cfg_path = getattr(args, "config", None) or getattr(args, "locateanything_config", None)
        path = Path(cfg_path) if cfg_path else DEFAULT_LA_CFG
        cfg = load_locateanything_config(path)
        every = getattr(args, "every_n_frames", None) or getattr(args, "la_every_n_frames", None)
        if every:
            cfg["every_n_frames"] = int(every)
        device = args.device if str(args.device).lower().startswith("cuda") else "cuda:0"
        if str(args.device).lower() in ("auto", "0"):
            device = "cuda:0"
        backend = LocateAnythingBackend(cfg, device=device)
        backend.load()
        return backend
