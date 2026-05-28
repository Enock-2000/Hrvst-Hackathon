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
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

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
    p.add_argument(
        "--alerts",
        action="store_true",
        help="Enable truck-arrival POST alerts (requires ARRIVAL_API_* env; use .\\alerts.ps1)",
    )
    p.add_argument(
        "--violation-alerts",
        action="store_true",
        help="Enable PPE/quality POST alerts to /api/v1/ppe/violations (VIOLATION_API_* or ARRIVAL_API_*)",
    )
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
    from alerts import ArrivalAlertTracker
    from violation_alerts import ViolationAlertTracker

    alert_tracker: ArrivalAlertTracker | None = None
    if args.alerts:
        alert_tracker = ArrivalAlertTracker.from_env(cam_id, required=True)
        print(f"  Arrival alerts: enabled -> {alert_tracker.describe()}")
    else:
        alert_tracker = ArrivalAlertTracker.from_env(cam_id, required=False)
        if alert_tracker:
            print(f"  Arrival alerts: enabled -> {alert_tracker.describe()}")

    violation_tracker: ViolationAlertTracker | None = None
    if args.violation_alerts:
        violation_tracker = ViolationAlertTracker.from_env(cam_id, required=True)
        print(f"  Violation alerts: enabled -> {violation_tracker.describe()}")
    else:
        violation_tracker = ViolationAlertTracker.from_env(cam_id, required=False)
        if violation_tracker:
            print(f"  Violation alerts: enabled -> {violation_tracker.describe()}")

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

            if alert_tracker:
                alert_tracker.maybe_alert(frame_idx, names, result.boxes)
            if violation_tracker:
                violation_tracker.maybe_alert(frame_idx, names, result.boxes)

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
                "  2. .\\Start-PackHouse.ps1 or .\\alerts.ps1  (waits for frames before YOLO)\n"
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
