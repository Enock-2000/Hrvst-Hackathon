from __future__ import annotations

import cv2
import numpy as np

from detectors.types import BoxDetection, FrameDetections


def _color_for_label(label: str) -> tuple[int, int, int]:
    palette = [
        (178, 145, 8),
        (38, 38, 220),
        (74, 163, 22),
        (235, 99, 37),
        (6, 119, 217),
        (234, 51, 147),
    ]
    idx = sum(ord(c) for c in label) % len(palette)
    return palette[idx]


def annotate_frame(
    frame_bgr: np.ndarray,
    detections: FrameDetections,
    *,
    line_width: int = 2,
    show_conf: bool = True,
) -> np.ndarray:
    out = frame_bgr.copy()
    for box in detections.boxes:
        x1, y1 = int(box.x1), int(box.y1)
        x2, y2 = int(box.x2), int(box.y2)
        color = _color_for_label(box.label)
        cv2.rectangle(out, (x1, y1), (x2, y2), color, line_width)
        text = box.label if not show_conf else f"{box.label} {box.confidence:.2f}"
        cv2.rectangle(out, (x1, max(0, y1 - 22)), (x1 + 8 * len(text) + 8, y1), color, -1)
        cv2.putText(
            out,
            text,
            (x1 + 4, y1 - 6),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
    return out


def filter_detections(
    detections: FrameDetections,
    *,
    min_conf: float,
    min_area_px: int = 0,
) -> FrameDetections:
    kept: list[BoxDetection] = []
    for box in detections.boxes:
        if box.confidence < min_conf:
            continue
        area = max(0.0, box.x2 - box.x1) * max(0.0, box.y2 - box.y1)
        if area < min_area_px:
            continue
        kept.append(box)
    return FrameDetections(boxes=kept)
