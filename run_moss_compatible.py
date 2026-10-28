"""Compatibility entry point; upstream source and weights stay unchanged."""
import runpy
import sys
from pathlib import Path
source = Path(__file__).resolve().parent / ".runtime/source/ComfyUI-master"
sys.path.insert(0, str(source))
# Python 3.12 platform.machine() can hang forever on a stalled WMI provider.
# Keep this compatibility override local to inference; stdlib falls back to WinAPI/registry.
if sys.platform == "win32":
    import platform
    def _without_wmi(*args, **kwargs):
        raise OSError("WMI disabled for local inference; use stdlib fallback")
    if hasattr(platform, "_wmi_query"):
        platform._wmi_query = _without_wmi

import comfy.options
comfy.options.enable_args_parsing()
import cuda_malloc  # configure the allocator BEFORE importing torch
import torch
import comfy_kitchen
import safetensors
_original_safe_open = safetensors.safe_open
def _safe_open_compatible(filename, framework, device="cpu", **kwargs):
    if framework in ("pt", "pytorch") and str(device) == "cpu":
        kwargs["backend"] = "pread"
    return _original_safe_open(filename, framework=framework, device=device, **kwargs)
safetensors.safe_open = _safe_open_compatible

# CUDA 13 kitchen attention bypasses the registry disabled by ComfyUI on cu128.
if torch.version.cuda and int(torch.version.cuda.split(".")[0]) < 13:
    comfy_kitchen.int8_attention_is_available = lambda device=None: False
    print("MOSS compatibility: CUDA<13 -> PyTorch attention", flush=True)

source = Path(__file__).resolve().parent / ".runtime/source/ComfyUI-master"
sys.path.insert(0, str(source))
runpy.run_path(str(source / "main.py"), run_name="__main__")
