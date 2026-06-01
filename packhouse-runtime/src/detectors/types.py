from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BoxDetection:
    label: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass
class FrameDetections:
    boxes: list[BoxDetection] = field(default_factory=list)

    def arrival_signal(self, trigger_labels: set[str] | None = None) -> tuple[str, float] | None:
        labels = trigger_labels or {"car", "truck", "vehicle"}
        best: tuple[str, float] | None = None
        for box in self.boxes:
            if box.label.lower() not in labels:
                continue
            if best is None or box.confidence > best[1]:
                best = (box.label, box.confidence)
        return best

    def summary_counts(self, focus: set[str] | None = None) -> dict[str, int]:
        focus = focus or {"car", "truck"}
        counts: dict[str, int] = {}
        for box in self.boxes:
            key = box.label.lower()
            if key in focus or box.label in focus:
                counts[box.label] = counts.get(box.label, 0) + 1
        return counts
