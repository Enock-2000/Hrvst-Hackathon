"""Parse LocateAnything model text output into pixel boxes + labels."""

from __future__ import annotations

import re

from detectors.types import BoxDetection

_BOX_TAG_RE = re.compile(
    r"<box>\s*<(\d+)>\s*<(\d+)>\s*<(\d+)>\s*<(\d+)>\s*</box>",
    re.IGNORECASE,
)
_REF_SEMANTIC_RE = re.compile(r"<ref>\s*(.*?)\s*</ref>", re.IGNORECASE | re.DOTALL)
_NUMERIC_IN_BOX_RE = re.compile(r"<\s*([0-9]+(?:\.[0-9]+)?)\s*>")


def _norm_label(raw: str) -> str:
    return re.sub(r"\s+", " ", raw).strip().lower()


def parse_mixed_results(answer: str, categories: list[str]) -> list[dict]:
    """
    Parse structured LocateAnything output (semantic + box blocks).
    Coordinates are normalized to [0, 1000] unless noted otherwise.
    """
    results: list[dict] = []
    expected = [c.strip().lower() for c in categories if c.strip()]
    category_str = " ".join(expected)
    current_label: str | None = None
    found_structured = False

    ref_box_pattern = r"(<ref>.*?</ref>)|(<box>.*?</box>)"
    for m in re.finditer(ref_box_pattern, answer, flags=re.IGNORECASE | re.DOTALL):
        token = m.group(0)
        if token.lower().startswith("<ref"):
            label_raw = re.sub(r"</?ref>", "", token, flags=re.IGNORECASE).strip()
            if label_raw:
                current_label = _norm_label(label_raw)
        else:
            content = re.sub(r"</?box>", "", token, flags=re.IGNORECASE)
            nums = [float(n) for n in _NUMERIC_IN_BOX_RE.findall(content)]
            if not nums:
                continue
            label = current_label or (expected[0] if expected else "object")
            if len(nums) == 4:
                results.append({"type": "box", "coords": nums, "label": label})
            elif len(nums) == 2:
                results.append({"type": "point", "coords": nums, "label": label})
            found_structured = True

    if found_structured:
        return results

    for m in _BOX_TAG_RE.finditer(answer):
        x1, y1, x2, y2 = (int(g) for g in m.groups())
        label = expected[0] if expected else "object"
        start = max(0, m.start() - 80)
        context = answer[start : m.start()].lower()
        for cat in expected:
            if cat in context:
                label = cat
                break
        results.append(
            {"type": "box", "coords": [float(x1), float(y1), float(x2), float(y2)], "label": label}
        )

    if results:
        return results

    box_pattern = r"<box>(.*?)</box>"
    parts = re.split(box_pattern, answer, flags=re.IGNORECASE | re.DOTALL)
    for i in range(1, len(parts), 2):
        preceding = parts[i - 1].lower()
        content = parts[i]
        label = expected[0] if expected else "object"
        for cat in expected:
            if cat in preceding:
                label = cat
                break
        nums = [float(n) for n in _NUMERIC_IN_BOX_RE.findall(content)]
        if len(nums) == 4:
            results.append({"type": "box", "coords": nums, "label": label})

    if not results and expected:
        # README fallback: plain <box> x1 y1 x2 y2 without semantic blocks
        for raw in _BOX_TAG_RE.findall(answer):
            x1, y1, x2, y2 = (int(v) for v in raw)
            results.append(
                {
                    "type": "box",
                    "coords": [float(x1), float(y1), float(x2), float(y2)],
                    "label": expected[0],
                }
            )

    _ = category_str  # used by callers for prompts; kept for API symmetry
    return results


def detections_from_answer(
    answer: str,
    image_width: int,
    image_height: int,
    categories: list[str],
    *,
    default_confidence: float = 1.0,
) -> list[BoxDetection]:
    parsed = parse_mixed_results(answer, categories)
    out: list[BoxDetection] = []
    w, h = image_width, image_height
    for item in parsed:
        if item.get("type") != "box":
            continue
        c = item["coords"]
        if len(c) != 4:
            continue
        if max(c) <= 1000.0:
            x1 = c[0] / 1000.0 * w
            y1 = c[1] / 1000.0 * h
            x2 = c[2] / 1000.0 * w
            y2 = c[3] / 1000.0 * h
        else:
            x1, y1, x2, y2 = c
        label = str(item.get("label", categories[0] if categories else "object"))
        out.append(
            BoxDetection(
                label=label,
                confidence=default_confidence,
                x1=float(x1),
                y1=float(y1),
                x2=float(x2),
                y2=float(y2),
            )
        )
    return out
