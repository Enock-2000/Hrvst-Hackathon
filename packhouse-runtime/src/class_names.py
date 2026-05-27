"""Load readable class names for YOLO model output."""

from __future__ import annotations

from pathlib import Path

import yaml

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
CLASS_NAMES_PATH = RUNTIME_ROOT / "config" / "class_names.yaml"


def _load_yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def load_class_config() -> dict:
    return _load_yaml(CLASS_NAMES_PATH)


def display_name_map() -> dict[int, str]:
    """ID → snake_case name for boxes and logs."""
    cfg = load_class_config()
    raw = cfg.get("display_names") or {}
    return {int(k): str(v) for k, v in raw.items()}


def label_map() -> dict[int, str]:
    """ID → title-case label for reports."""
    cfg = load_class_config()
    raw = cfg.get("labels") or cfg.get("display_names") or {}
    return {int(k): str(v) for k, v in raw.items()}


def apply_names_to_model(model) -> dict[int, str]:
    """
    Replace underlying model.names with readable display_names for plotting and exports.
    Returns the applied mapping.
    """
    mapping = display_name_map()
    if not mapping:
        return dict(model.names)

    base = getattr(model, "model", None)
    names_dict = getattr(base, "names", None) if base is not None else None
    if not isinstance(names_dict, dict):
        names_dict = dict(model.names)

    new_names: dict[int, str] = {}
    for i in range(len(names_dict)):
        old = names_dict.get(i, model.names.get(i, f"class_{i}"))
        new_names[i] = mapping.get(i, str(old))

    if base is not None and hasattr(base, "names"):
        base.names = new_names
    return new_names


def remap_counter(counts: dict[str, int]) -> dict[str, int]:
    """Remap raw model name keys to display names (if config differs)."""
    cfg = load_class_config()
    training = cfg.get("model_training_names") or {}
    display = cfg.get("display_names") or {}
    if not training:
        return counts
    rev = {str(v): display.get(int(k), str(v)) for k, v in training.items()}
    out: dict[str, int] = {}
    for name, n in counts.items():
        out[rev.get(name, name)] = out.get(rev.get(name, name), 0) + n
    return out
