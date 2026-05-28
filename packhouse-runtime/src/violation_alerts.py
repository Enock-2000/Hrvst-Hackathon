"""
PPE / safety / produce-quality violation alerts.

POST /api/v1/ppe/violations when mapped YOLO classes are detected.
Separate from truck-arrival alerts in alerts.py.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from alert_http import post_json

VIOLATION_PATH = "/api/v1/ppe/violations"
CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "violation_alerts.yaml"
CAMERAS_PATH = Path(__file__).resolve().parents[1] / "config" / "cameras.yaml"


def read_float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        print(f"Invalid {name}='{raw}', using default {default}.", file=sys.stderr)
        return default


def load_violation_label_map() -> dict[str, str]:
    if not CONFIG_PATH.is_file():
        return {"no_ppe": "no_hairnet", "rotten_produce": "rotten_produce"}
    with CONFIG_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    raw = data.get("label_to_violation_type") or {}
    return {str(k): str(v) for k, v in raw.items() if v}


def resolve_api_camera_id(camera_key: str) -> str:
    if CAMERAS_PATH.is_file():
        with CAMERAS_PATH.open(encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        cam = (cfg.get("cameras") or {}).get(camera_key) or {}
        api_id = cam.get("api_camera_id")
        if api_id:
            return str(api_id)
    return camera_key


def load_violation_alert_config(*, required: bool = False) -> dict[str, float | str] | None:
    base_url = (
        os.getenv("VIOLATION_API_BASE_URL", "").strip()
        or os.getenv("ARRIVAL_API_BASE_URL", "").strip()
    )
    bearer_token = (
        os.getenv("VIOLATION_API_BEARER_TOKEN", "").strip()
        or os.getenv("ARRIVAL_API_BEARER_TOKEN", "").strip()
    )
    if not base_url or not bearer_token:
        if required:
            raise RuntimeError(
                "Set VIOLATION_API_BASE_URL and VIOLATION_API_BEARER_TOKEN "
                "(or ARRIVAL_API_* as fallback) in .env."
            )
        print(
            "  Violation alerts: disabled (set VIOLATION_API_* or ARRIVAL_API_* in .env).",
            file=sys.stderr,
        )
        return None
    return {
        "base_url": base_url.rstrip("/"),
        "bearer_token": bearer_token,
        "cooldown_sec": read_float_env("VIOLATION_ALERT_COOLDOWN_SEC", 30.0),
        "timeout_sec": read_float_env(
            "VIOLATION_ALERT_TIMEOUT_SEC",
            read_float_env("ARRIVAL_ALERT_TIMEOUT_SEC", 5.0),
        ),
    }


def detect_violation_signals(
    names: dict, boxes, label_map: dict[str, str]
) -> list[tuple[str, float, str]]:
    """Return list of (violation_type, confidence, source_label)."""
    if boxes is None or len(boxes) == 0:
        return []
    confs = boxes.conf.tolist() if boxes.conf is not None else []
    best_by_type: dict[str, tuple[float, str]] = {}
    for idx, cls_id in enumerate(boxes.cls.int().tolist()):
        label = names[int(cls_id)]
        violation_type = label_map.get(label)
        if not violation_type:
            continue
        conf = float(confs[idx]) if idx < len(confs) else 0.0
        prev = best_by_type.get(violation_type)
        if prev is None or conf > prev[0]:
            best_by_type[violation_type] = (conf, label)
    return [(vtype, conf, src) for vtype, (conf, src) in best_by_type.items()]


def build_violation_payload(
    camera_id: str,
    violation_type: str,
    confidence: float,
) -> dict[str, Any]:
    return {
        "cameraId": camera_id,
        "violationType": violation_type,
        "confidence": round(confidence, 4),
        "detectedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "imageUrl": None,
        "metadata": None,
    }


def post_violation_alert(
    config: dict[str, float | str],
    camera_id: str,
    violation_type: str,
    confidence: float,
) -> bool:
    payload = build_violation_payload(camera_id, violation_type, confidence)
    return post_json(
        base_url=str(config["base_url"]),
        path=VIOLATION_PATH,
        bearer_token=str(config["bearer_token"]),
        payload=payload,
        timeout_sec=float(config["timeout_sec"]),
        log_label=f"Violation alert ({violation_type}, cameraId={camera_id})",
    )


class ViolationAlertTracker:
    """Cooldown-gated violation POSTs per violationType + camera."""

    def __init__(
        self,
        config: dict[str, float | str],
        camera_key: str,
        label_map: dict[str, str] | None = None,
    ) -> None:
        self.config = config
        self.camera_key = camera_key
        self.api_camera_id = resolve_api_camera_id(camera_key)
        self.label_map = label_map or load_violation_label_map()
        self._last_sent_by_type: dict[str, float] = {}

    @classmethod
    def from_env(cls, camera_key: str, *, required: bool = False) -> ViolationAlertTracker | None:
        config = load_violation_alert_config(required=required)
        if config is None:
            return None
        return cls(config, camera_key)

    def describe(self) -> str:
        types = ", ".join(sorted(set(self.label_map.values())))
        return (
            f"{self.config['base_url']}{VIOLATION_PATH} "
            f"cameraId={self.api_camera_id} types=[{types}] "
            f"cooldown={self.config['cooldown_sec']}s"
        )

    def maybe_alert(self, frame_idx: int, names: dict, boxes) -> int:
        signals = detect_violation_signals(names, boxes, self.label_map)
        if not signals:
            return 0
        now = time.time()
        cooldown_sec = float(self.config["cooldown_sec"])
        sent = 0
        for violation_type, conf, source_label in signals:
            last = self._last_sent_by_type.get(violation_type, 0.0)
            if now - last < cooldown_sec:
                continue
            print(
                f"  [frame {frame_idx}] violation {violation_type} "
                f"(from {source_label}, conf={conf:.2f}); posting {VIOLATION_PATH}"
            )
            post_violation_alert(self.config, self.api_camera_id, violation_type, conf)
            self._last_sent_by_type[violation_type] = now
            sent += 1
        return sent
