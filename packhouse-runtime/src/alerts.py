"""
Truck-arrival alerts: detect vehicle/plate signals and POST to receiving API.

Run independently from repo root:
  .\\alerts.ps1

Or import from live_inference when alerts are enabled via environment variables.
"""

from __future__ import annotations

import json
import os
import sys
import time
from urllib import error as url_error
from urllib import request as url_request

TRUCK_ARRIVAL_PATH = "/api/v1/receiving/truck-arrivals"
TRIGGER_LABELS = frozenset({"license_plate", "car", "vehicle"})


def read_float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        print(f"Invalid {name}='{raw}', using default {default}.", file=sys.stderr)
        return default


def load_arrival_alert_config(*, required: bool = False) -> dict[str, float | str] | None:
    base_url = os.getenv("ARRIVAL_API_BASE_URL", "").strip()
    bearer_token = os.getenv("ARRIVAL_API_BEARER_TOKEN", "").strip()
    if not base_url or not bearer_token:
        if required:
            raise RuntimeError(
                "ARRIVAL_API_BASE_URL and ARRIVAL_API_BEARER_TOKEN must be set (use .\\alerts.ps1 or .env)."
            )
        print("  Arrival alerts: disabled (set ARRIVAL_API_BASE_URL and ARRIVAL_API_BEARER_TOKEN).")
        return None
    return {
        "base_url": base_url.rstrip("/"),
        "bearer_token": bearer_token,
        "cooldown_sec": read_float_env("ARRIVAL_ALERT_COOLDOWN_SEC", 30.0),
        "timeout_sec": read_float_env("ARRIVAL_ALERT_TIMEOUT_SEC", 5.0),
    }


def detect_arrival_signal(names: dict, boxes) -> tuple[str, float] | None:
    if boxes is None or len(boxes) == 0:
        return None
    best: tuple[str, float] | None = None
    confs = boxes.conf.tolist() if boxes.conf is not None else []
    for idx, cls_id in enumerate(boxes.cls.int().tolist()):
        label = names[int(cls_id)]
        if label.lower() not in TRIGGER_LABELS:
            continue
        conf = float(confs[idx]) if idx < len(confs) else 0.0
        if best is None or conf > best[1]:
            best = (label, conf)
    return best


def build_truck_arrival_payload(camera_id: str, truck_plate: str = "UNKNOWN") -> dict:
    return {
        "truckPlate": truck_plate,
        "gateCameraId": camera_id,
        "suggestedOrderIds": [],
    }


def post_truck_arrival_alert(config: dict[str, float | str], camera_id: str) -> bool:
    payload = build_truck_arrival_payload(camera_id)
    req = url_request.Request(
        url=f"{config['base_url']}{TRUCK_ARRIVAL_PATH}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config['bearer_token']}",
        },
        method="POST",
    )
    timeout_sec = float(config["timeout_sec"])
    try:
        with url_request.urlopen(req, timeout=timeout_sec) as resp:
            status = resp.getcode()
        print(f"  Arrival alert sent (status={status}, gateCameraId={camera_id}).")
        return True
    except url_error.HTTPError as e:
        print(f"  Arrival alert failed: HTTP {e.code} {e.reason}", file=sys.stderr)
    except url_error.URLError as e:
        print(f"  Arrival alert failed: {e.reason}", file=sys.stderr)
    return False


class ArrivalAlertTracker:
    """Cooldown-gated truck-arrival POSTs for a single camera stream."""

    def __init__(self, config: dict[str, float | str], camera_id: str) -> None:
        self.config = config
        self.camera_id = camera_id
        self._last_sent_ts = 0.0

    @classmethod
    def from_env(cls, camera_id: str, *, required: bool = False) -> ArrivalAlertTracker | None:
        config = load_arrival_alert_config(required=required)
        if config is None:
            return None
        return cls(config, camera_id)

    def describe(self) -> str:
        return (
            f"{self.config['base_url']}{TRUCK_ARRIVAL_PATH} "
            f"(cooldown={self.config['cooldown_sec']}s)"
        )

    def maybe_alert(self, frame_idx: int, names: dict, boxes) -> bool:
        signal = detect_arrival_signal(names, boxes)
        if not signal:
            return False
        now = time.time()
        cooldown_sec = float(self.config["cooldown_sec"])
        if now - self._last_sent_ts < cooldown_sec:
            return False
        label, conf = signal
        print(
            f"  [frame {frame_idx}] arrival trigger={label} conf={conf:.2f}; "
            f"posting {TRUCK_ARRIVAL_PATH}"
        )
        post_truck_arrival_alert(self.config, self.camera_id)
        self._last_sent_ts = now
        return True
