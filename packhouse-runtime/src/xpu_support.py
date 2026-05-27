"""Minimal Intel XPU patch for Ultralytics predict (inference only)."""


def patch_ultralytics_xpu_select_device() -> None:
    import torch
    import ultralytics.utils.torch_utils as torch_utils

    if getattr(torch_utils.select_device, "_xpu_patched", False):
        return

    _original = torch_utils.select_device

    def select_device(device="", batch=0, verbose=True):
        dev_str = str(device).strip().lower()
        if dev_str.startswith("xpu"):
            if not hasattr(torch, "xpu") or not torch.xpu.is_available():
                raise ValueError(
                    "Intel XPU requested but torch.xpu.is_available() is False."
                )
            idx = 0
            if ":" in dev_str:
                idx = int(dev_str.split(":", maxsplit=1)[1])
            dev = torch.device(f"xpu:{idx}")
            if verbose:
                name = torch.xpu.get_device_name(idx)
                print(f"Using Intel XPU:{idx} ({name})")
            return dev
        return _original(device, batch, verbose)

    select_device._xpu_patched = True  # type: ignore[attr-defined]
    torch_utils.select_device = select_device
