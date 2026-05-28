"""
Live pack house detection on RTSP camera streams (Eufy bridge → go2rtc → YOLO).

Prerequisites:
  1. Docker bridge running (or run .\\Start-PackHouse.ps1 from repo root)
  2. Model at packhouse-runtime/models/packhouse_best.pt

Run from repo root:
  .\\Start-PackHouse.ps1
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib import error as url_error
from urllib import request as url_request

import yaml

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = RUNTIME_ROOT / "models" / "packhouse_best.pt"
CONFIG_PATH = RUNTIME_ROOT / "config" / "cameras.yaml"
RUNS_DIR = RUNTIME_ROOT / "runs" / "live"

CORE_CLASSES = {
    "produce_crate",
    "fruit_vegetable",
    "fresh_produce",
    "rotten_produce",
    "license_plate",
    "worker",
    "ppe",
    "no_ppe",
}


def read_float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        print(f"Invalid {name}='{raw}', using default {default}.", file=sys.stderr)
        return default


def load_arrival_alert_config() -> dict[str, float | str] | None:
    base_url = os.getenv("ARRIVAL_API_BASE_URL", "").strip()
    bearer_token = os.getenv("ARRIVAL_API_BEARER_TOKEN", "").strip()
    if not base_url or not bearer_token:
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
    trigger_labels = {"license_plate", "car", "vehicle"}
    best: tuple[str, float] | None = None
    confs = boxes.conf.tolist() if boxes.conf is not None else []
    for idx, cls_id in enumerate(boxes.cls.int().tolist()):
        label = names[int(cls_id)]
        if label.lower() not in trigger_labels:
            continue
        conf = float(confs[idx]) if idx < len(confs) else 0.0
        if best is None or conf > best[1]:
            best = (label, conf)
    return best


def post_truck_arrival_alert(config: dict[str, float | str], camera_id: str) -> bool:
    payload = {
        "truckPlate": "UNKNOWN",
        "gateCameraId": camera_id,
        "suggestedOrderIds": [],
    }
    req = url_request.Request(
        url=f"{config['base_url']}/api/v1/receiving/truck-arrivals",
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


def load_cameras_config() -> dict:
    if not CONFIG_PATH.is_file():
        raise FileNotFoundError(f"Missing camera config: {CONFIG_PATH}")
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_rtsp(camera_id: str | None, rtsp_override: str | None) -> tuple[str, str]:
    if rtsp_override:
        return rtsp_override, "custom"
    cfg = load_cameras_config()
    cam_key = camera_id or cfg.get("default_camera", "entrance")
    cameras = cfg.get("cameras") or {}
    if cam_key not in cameras:
        raise KeyError(f"Unknown camera '{cam_key}'. Options: {list(cameras)}")
    cam = cameras[cam_key]
    return cam["rtsp"], cam_key


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="YOLO live inference on pack house RTSP streams.")
    p.add_argument("--camera", default=None, help="Camera id from config/cameras.yaml")
    p.add_argument("--rtsp", default=None, help="Override RTSP URL")
    p.add_argument("--model", type=Path, default=DEFAULT_MODEL, help="Path to .pt weights")
    p.add_argument("--conf", type=float, default=0.35, help="Detection confidence threshold")
    p.add_argument("--device", default="cpu", help="cpu, 0, cuda:0, or xpu")
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--track", action="store_true", help="Use ByteTrack (persist IDs across frames)")
    p.add_argument(
        "--show",
        action="store_true",
        help="Live window with bounding boxes + class labels (press Q to quit)",
    )
    p.add_argument("--line-width", type=int, default=2, help="Bounding box line width when --show")
    p.add_argument(
        "--save",
        action="store_true",
        default=True,
        help="Save annotated frames/video under runs/live/ (default: on)",
    )
    p.add_argument("--no-save", action="store_true", help="Disable saving outputs")
    p.add_argument("--name", default=None, help="Run subfolder name under runs/live/")
    p.add_argument("--log-every", type=int, default=30, help="Print detection summary every N frames")
    p.add_argument("--max-frames", type=int, default=0, help="Stop after N frames (0 = unlimited)")
    return p.parse_args()


def print_detection_summary(frame_idx: int, names: dict, boxes) -> None:
    if boxes is None or len(boxes) == 0:
        print(f"  [frame {frame_idx}] no detections")
        return
    counts: Counter[str] = Counter()
    for cls_id in boxes.cls.int().tolist():
        counts[names[int(cls_id)]] += 1
    parts = [f"{k}={v}" for k, v in counts.most_common()]
    core = [p for p in parts if p.split("=")[0] in CORE_CLASSES]
    produce = [
        p
        for p in parts
        if p.split("=")[0] not in CORE_CLASSES
        and any(x in p.split("=")[0] for x in ("fresh_", "rotten_", "stale_"))
    ]
    other = [p for p in parts if p not in core and p not in produce]
    line = ", ".join(core) if core else ""
    if produce:
        line += ("" if not line else " | ") + "produce: " + ", ".join(produce)
    if not line:
        line = "(no detections above threshold)"
    if other:
        line += f" | other: {', '.join(other)}"
    print(f"  [frame {frame_idx}] {line}")


def main() -> int:
    args = parse_args()
    if args.no_save:
        args.save = False

    if not args.model.is_file():
        print(f"Model not found: {args.model}", file=sys.stderr)
        print("Place packhouse_best.pt in packhouse-runtime/models/ or pass --model", file=sys.stderr)
        return 1

    try:
        rtsp_url, cam_id = resolve_rtsp(args.camera, args.rtsp)
    except (FileNotFoundError, KeyError) as e:
        print(e, file=sys.stderr)
        return 1

    if str(args.device).lower().startswith("xpu"):
        from xpu_support import patch_ultralytics_xpu_select_device

        patch_ultralytics_xpu_select_device()

    from ultralytics import YOLO

    run_name = args.name or f"{cam_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    print("Pack House — Live YOLO inference")
    print(f"  Camera:   {cam_id}")
    print(f"  RTSP:     {rtsp_url}")
    print(f"  Model:    {args.model}")
    print(f"  Device:   {args.device}")
    print(f"  Conf:     {args.conf}")
    print(f"  Track:    {args.track}")
    print(f"  Save:     {args.save} → {RUNS_DIR / run_name}")
    print("  Press Ctrl+C to stop.\n")

    from class_names import apply_names_to_model

    model = YOLO(str(args.model))
    apply_names_to_model(model)
    names = model.names
    print(f"  Classes:     {', '.join(names[i] for i in range(len(names)))}")
    alert_config = load_arrival_alert_config()
    last_arrival_alert_ts = 0.0
    if alert_config:
        print(
            "  Arrival alerts: enabled -> "
            f"{alert_config['base_url']}/api/v1/receiving/truck-arrivals "
            f"(cooldown={alert_config['cooldown_sec']}s)"
        )

    predict_kw: dict = {
        "source": rtsp_url,
        "stream": True,
        "conf": args.conf,
        "imgsz": args.imgsz,
        "device": args.device,
        "verbose": False,
    }
    if args.save:
        predict_kw.update(project=str(RUNS_DIR), name=run_name, save=True)

    # Warm-up: go2rtc may need a consumer before frames flow steadily
    print("Connecting to stream (waiting for first frames)...")
    if args.show:
        print("  Live view: bounding boxes + labels. Press Q in the video window to quit.")
    t0 = time.time()
    frame_idx = 0
    window_name = f"Pack House Live — {cam_id}"

    try:
        import cv2

        runner = model.track(**predict_kw, persist=True) if args.track else model.predict(**predict_kw)
        for result in runner:
            frame_idx += 1
            if frame_idx == 1:
                print(f"  Stream active after {time.time() - t0:.1f}s")

            # Real-time annotated frame: boxes, class names, confidence (and track IDs if --track)
            if args.show:
                annotated = result.plot(line_width=args.line_width, labels=True, boxes=True)
                cv2.imshow(window_name, annotated)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), ord("Q"), 27):
                    print("Quit key pressed.")
                    break

            if args.log_every > 0 and frame_idx % args.log_every == 0:
                print_detection_summary(frame_idx, names, result.boxes)

            signal = detect_arrival_signal(names, result.boxes)
            if signal and alert_config:
                now = time.time()
                cooldown_sec = float(alert_config["cooldown_sec"])
                if now - last_arrival_alert_ts >= cooldown_sec:
                    label, conf = signal
                    print(
                        f"  [frame {frame_idx}] arrival trigger={label} conf={conf:.2f}; "
                        "posting /api/v1/receiving/truck-arrivals"
                    )
                    post_truck_arrival_alert(alert_config, cam_id)
                    last_arrival_alert_ts = now

            if args.max_frames > 0 and frame_idx >= args.max_frames:
                print(f"Stopped after {args.max_frames} frames.")
                break
        if args.show:
            cv2.destroyAllWindows()
    except KeyboardInterrupt:
        print("\nStopped by user.")
    except Exception as e:
        err = str(e).lower()
        print(f"\nStream error: {e}", file=sys.stderr)
        if "404" in err or "describe failed" in err:
            print(
                "RTSP stream not ready (camera bridge). From repo root:\n"
                "  1. Fill and SAVE .env (EUFY_USERNAME, EUFY_PASSWORD, EUFY_COUNTRY)\n"
                "  2. .\\Start-PackHouse.ps1  (waits for frames before YOLO)\n"
                "  3. Test: http://localhost:1984/stream.html?src=living_room",
                file=sys.stderr,
            )
        else:
            print("Check: docker compose ps (repo root), open http://localhost:1984/", file=sys.stderr)
        return 1

    print(f"Processed {frame_idx} frames.")
    if args.save:
        print(f"Outputs: {RUNS_DIR / run_name}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
