"""
Live pack house detection: Eufy → go2rtc → NVIDIA LocateAnything-3B (CUDA).

  .\\Start-PackHouse.ps1
  python src\\live_inference.py --device cuda --show --camera entrance
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib import error as url_error
from urllib import request as url_request

import yaml

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = RUNTIME_ROOT / "config" / "cameras.yaml"
LA_CFG_PATH = RUNTIME_ROOT / "config" / "locateanything.yaml"
LOCAL_MODEL_DIR = RUNTIME_ROOT / "models" / "LocateAnything-3B"

CORE_CLASSES = {"car", "truck"}


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
    try:
        with url_request.urlopen(req, timeout=float(config["timeout_sec"])) as resp:
            print(f"  Arrival alert sent (status={resp.getcode()}, gateCameraId={camera_id}).")
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


def go2rtc_src_for_camera(cam_id: str, cam: dict) -> str:
    if cam.get("go2rtc_src"):
        return str(cam["go2rtc_src"])
    path = cam.get("rtsp", "").rstrip("/").split("/")
    return path[-1] if path else cam_id


def list_configured_cameras() -> list[tuple[str, dict]]:
    cfg = load_cameras_config()
    cameras = cfg.get("cameras") or {}
    if not cameras:
        raise KeyError("No cameras defined in config/cameras.yaml")
    return list(cameras.items())


def resolve_rtsp(camera_id: str | None, rtsp_override: str | None) -> tuple[str, str]:
    if rtsp_override:
        return rtsp_override, "custom"
    cfg = load_cameras_config()
    cam_key = camera_id or cfg.get("default_camera", "entrance")
    cameras = cfg.get("cameras") or {}
    if cam_key not in cameras:
        raise KeyError(f"Unknown camera '{cam_key}'. Options: {list(cameras)}")
    return cameras[cam_key]["rtsp"], cam_key


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="LocateAnything live detection on pack house streams.")
    p.add_argument("--camera", default=None, help="Camera id from config/cameras.yaml")
    p.add_argument("--all-cameras", action="store_true", help="Split-screen for all cameras")
    p.add_argument("--rtsp", default=None, help="Override RTSP URL")
    p.add_argument("--panel-width", type=int, default=960)
    p.add_argument("--device", default="cuda:0", help="cuda:0 (NVIDIA GPU required)")
    p.add_argument("--config", type=Path, default=LA_CFG_PATH, help="locateanything.yaml path")
    p.add_argument("--every-n-frames", type=int, default=None, help="Override every_n_frames in config")
    p.add_argument("--show", action="store_true", help="Live window (Q to quit)")
    p.add_argument("--line-width", type=int, default=2)
    p.add_argument("--save", action="store_true", default=True)
    p.add_argument("--no-save", action="store_true")
    p.add_argument("--log-every", type=int, default=30)
    p.add_argument("--max-frames", type=int, default=0)
    return p.parse_args()


def print_detection_summary(frame_idx: int, detections) -> None:
    counts = detections.summary_counts(CORE_CLASSES)
    if not counts:
        print(f"  [frame {frame_idx}] no detections")
        return
    parts = [f"{k}={v}" for k, v in sorted(counts.items(), key=lambda x: -x[1])]
    print(f"  [frame {frame_idx}] {', '.join(parts)}")


def _wake_go2rtc_stream(src: str) -> None:
    try:
        url_request.urlopen(f"http://127.0.0.1:1984/api/frame.jpeg?src={src}", timeout=8)
    except (url_error.URLError, TimeoutError, OSError):
        pass


class _Go2RtcSnapshotCapture:
    def __init__(self, src: str, interval_sec: float = 0.12):
        self._url = f"http://127.0.0.1:1984/api/frame.jpeg?src={src}"
        self.interval_sec = interval_sec
        self._last_read = 0.0
        self._last_frame = None

    def read(self):
        import cv2
        import numpy as np

        now = time.time()
        if self._last_frame is not None and (now - self._last_read) < self.interval_sec:
            return True, self._last_frame.copy()
        try:
            with url_request.urlopen(self._url, timeout=4) as resp:
                data = resp.read()
            frame = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                return False, None
            self._last_frame = frame
            self._last_read = now
            return True, frame
        except (url_error.URLError, TimeoutError, OSError):
            return False, None

    def release(self) -> None:
        self._last_frame = None


def _open_capture(rtsp_url: str, mjpeg_url: str | None, go2rtc_src: str | None = None):
    import cv2

    if go2rtc_src:
        _wake_go2rtc_stream(go2rtc_src)
        snap = _Go2RtcSnapshotCapture(go2rtc_src)
        ok, frame = snap.read()
        if ok and frame is not None:
            return snap, f"snapshot:{go2rtc_src}"

    for url in (mjpeg_url,):
        if not url:
            continue
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if cap.isOpened():
            ok, frame = cap.read()
            if ok and frame is not None:
                return cap, url
            cap.release()

    if rtsp_url:
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if cap.isOpened():
            ok, frame = cap.read()
            if ok and frame is not None:
                return cap, rtsp_url
            cap.release()
    return None, rtsp_url


def _mjpeg_fallback(rtsp_url: str) -> str | None:
    if "/8554/" not in rtsp_url:
        return None
    src = rtsp_url.rstrip("/").split("/")[-1]
    host = rtsp_url.split("/")[2].split(":")[0]
    return f"http://{host}:1984/api/stream.mjpeg?src={src}"


def _label_frame(frame, title: str):
    import cv2

    out = frame.copy()
    cv2.rectangle(out, (0, 0), (min(out.shape[1], len(title) * 11 + 16), 32), (0, 0, 0), -1)
    cv2.putText(out, title, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)
    return out


def _compose_split_screen(panels: list[tuple[str, object]], panel_width: int):
    import cv2
    import numpy as np

    if not panels:
        return np.zeros((480, 640, 3), dtype=np.uint8)
    cols = 1 if len(panels) == 1 else 2
    rows = (len(panels) + cols - 1) // cols
    resized = []
    for _, img in panels:
        h, w = img.shape[:2]
        scale = panel_width / max(w, 1)
        resized.append(cv2.resize(img, (panel_width, max(int(h * scale), 1))))
    max_h = max(t.shape[0] for t in resized)
    norm = []
    for tile in resized:
        pad = max_h - tile.shape[0]
        if pad > 0:
            tile = cv2.copyMakeBorder(tile, 0, pad, 0, 0, cv2.BORDER_CONSTANT, value=(0, 0, 0))
        norm.append(tile)
    blank = np.zeros((max_h, panel_width, 3), dtype=np.uint8)
    while len(norm) < rows * cols:
        norm.append(blank.copy())
    row_images = [np.hstack(norm[r * cols : (r + 1) * cols]) for r in range(rows)]
    max_w = max(r.shape[1] for r in row_images)
    aligned = []
    for row in row_images:
        pad_r = max_w - row.shape[1]
        if pad_r > 0:
            row = cv2.copyMakeBorder(row, 0, 0, 0, pad_r, cv2.BORDER_CONSTANT, value=(0, 0, 0))
        aligned.append(row)
    return aligned[0] if len(aligned) == 1 else np.vstack(aligned)


def _process_frame(detector, frame, args):
    detections = detector.predict(frame)
    annotated = detector.annotate(frame, detections, line_width=args.line_width)
    return detections, annotated


def _preflight_model() -> bool:
    if (LOCAL_MODEL_DIR / "config.json").is_file():
        print(f"  Model weights: {LOCAL_MODEL_DIR} (local)")
        return True
    print(f"  Model weights: not found at {LOCAL_MODEL_DIR}", file=sys.stderr)
    print("  Run: .\\scripts\\Download-LocateAnythingModel.ps1", file=sys.stderr)
    return False


def run_all_cameras(args: argparse.Namespace, detector) -> int:
    import cv2

    alert_config = load_arrival_alert_config()
    arrival_cooldowns: dict[str, float] = {}
    streams: list[dict] = []

    print("Pack House — LocateAnything (multi-camera)")
    print(f"  {detector.describe()}")
    print("  Connecting...")

    for cam_id, cam in list_configured_cameras():
        rtsp = cam["rtsp"]
        label = cam.get("name") or cam_id
        mjpeg = cam.get("http") or _mjpeg_fallback(rtsp)
        src = go2rtc_src_for_camera(cam_id, cam)
        cap, source = _open_capture(rtsp, mjpeg, go2rtc_src=src)
        if cap is None:
            print(f"  SKIP {cam_id}: no stream", file=sys.stderr)
            continue
        print(f"  {cam_id}: {label} ({source})")
        streams.append({"id": cam_id, "label": label, "cap": cap, "frame_idx": 0})

    if not streams:
        return 1

    frame_idx = 0
    try:
        while True:
            panels = []
            for s in streams:
                ok, frame = s["cap"].read()
                if not ok or frame is None:
                    continue
                s["frame_idx"] += 1
                detections, annotated = _process_frame(detector, frame, args)
                panels.append((s["id"], _label_frame(annotated, s["label"])))
                signal = detections.arrival_signal()
                if signal and alert_config:
                    now = time.time()
                    if now - arrival_cooldowns.get(s["id"], 0.0) >= float(alert_config["cooldown_sec"]):
                        post_truck_arrival_alert(alert_config, s["id"])
                        arrival_cooldowns[s["id"]] = now
            if not panels:
                time.sleep(0.05)
                continue
            frame_idx += 1
            if args.show:
                cv2.imshow("Pack House — All cameras", _compose_split_screen(panels, args.panel_width))
                if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q"), 27):
                    break
            if args.max_frames > 0 and frame_idx >= args.max_frames:
                break
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        for s in streams:
            s["cap"].release()
        if args.show:
            cv2.destroyAllWindows()
    return 0


def run_single_camera(args: argparse.Namespace, detector, cam_id: str, rtsp_url: str) -> int:
    import cv2

    cam = (load_cameras_config().get("cameras") or {}).get(cam_id, {})
    mjpeg = cam.get("http") or _mjpeg_fallback(rtsp_url)
    label = cam.get("name", cam_id)

    alert_config = load_arrival_alert_config()
    last_alert = 0.0

    print("Pack House — LocateAnything")
    print(f"  Camera: {label} ({cam_id})")
    print(f"  {detector.describe()}")

    cap, source = _open_capture(rtsp_url, mjpeg, go2rtc_src=go2rtc_src_for_camera(cam_id, cam))
    if cap is None:
        print(f"No stream at {rtsp_url}", file=sys.stderr)
        return 1
    print(f"  Stream: {source}\n")

    frame_idx = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                time.sleep(0.05)
                continue
            frame_idx += 1
            detections, annotated = _process_frame(detector, frame, args)
            if args.show:
                cv2.imshow(f"Pack House — {cam_id}", _label_frame(annotated, label))
                if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q"), 27):
                    break
            if args.log_every > 0 and frame_idx % args.log_every == 0:
                print_detection_summary(frame_idx, detections)
                if detector.last_inference_ms > 0:
                    print(f"  inference {detector.last_inference_ms:.0f} ms")
            signal = detections.arrival_signal()
            if signal and alert_config:
                now = time.time()
                if now - last_alert >= float(alert_config["cooldown_sec"]):
                    post_truck_arrival_alert(alert_config, cam_id)
                    last_alert = now
            if args.max_frames > 0 and frame_idx >= args.max_frames:
                break
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        cap.release()
        if args.show:
            cv2.destroyAllWindows()
    return 0


def main() -> int:
    import torch

    args = parse_args()
    if args.no_save:
        args.save = False

    if not _preflight_model():
        return 1

    if not torch.cuda.is_available():
        print(
            "CUDA GPU required for inference. Download weights on any PC, then run on NVIDIA hardware.",
            file=sys.stderr,
        )
        return 1

    device = args.device
    if str(device).lower() in ("auto", "0"):
        device = "cuda:0"

    args.locateanything_config = args.config
    args.la_every_n_frames = args.every_n_frames

    from detectors.factory import create_detector

    print("Loading LocateAnything...")
    try:
        detector = create_detector(args)
    except Exception as e:
        print(f"Failed to load model: {e}", file=sys.stderr)
        return 1

    use_all = args.all_cameras or (
        args.camera is not None and str(args.camera).lower() in ("all", "*")
    )
    if use_all:
        if not args.show:
            args.show = True
        return run_all_cameras(args, detector)

    try:
        rtsp_url, cam_id = resolve_rtsp(args.camera, args.rtsp)
    except (FileNotFoundError, KeyError) as e:
        print(e, file=sys.stderr)
        return 1

    if not args.show:
        args.show = True
    return run_single_camera(args, detector, cam_id, rtsp_url)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
