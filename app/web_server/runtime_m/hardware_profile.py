import os
import platform
import re
import shutil
import subprocess
from pathlib import Path

from .gguf_metadata import GgufMetadataError, read_gguf_metadata


class LocalHardwareProfile:
    GPU_MEMORY_SAFETY_RATIO = 0.88
    MODEL_NON_LAYER_OVERHEAD_RATIO = 0.12

    def snapshot(self):
        ram_gb = self._get_total_ram_gb()
        vram_gb = self._get_nvidia_vram_gb()
        machine = platform.machine() or ""
        system = platform.system() or ""
        is_apple_silicon = system == "Darwin" and machine.lower() in {"arm64", "aarch64"}

        return {
            "system": system,
            "machine": machine,
            "ram_gb": ram_gb,
            "vram_gb": vram_gb,
            "is_apple_silicon": is_apple_silicon,
            "memory_kind": "unified" if is_apple_silicon else ("vram" if vram_gb else "system"),
        }

    def resolve_llama_cpp_gpu_layers(self, model_path):
        hardware = self.snapshot()
        if hardware.get("is_apple_silicon"):
            return -1

        vram_gb = float(hardware.get("vram_gb") or 0)
        if vram_gb <= 0:
            return None

        return self._estimate_gpu_layers_for_vram(model_path, vram_gb)

    def llama_cpp_python_supports_gpu_offload(self):
        try:
            import llama_cpp
        except (ImportError, OSError):
            return False

        supports_gpu_offload = getattr(llama_cpp, "llama_supports_gpu_offload", None)
        if not callable(supports_gpu_offload):
            return False

        try:
            return bool(supports_gpu_offload())
        except Exception:
            return False

    def assess_model(self, entry):
        hardware = self.snapshot()
        required_ram_gb = self._estimate_required_ram_gb(entry)
        capacity_gb = hardware["vram_gb"] or hardware["ram_gb"]

        if not required_ram_gb or not capacity_gb:
            return self._assessment("yellow", "unknown", "Local memory could not be estimated.", required_ram_gb, hardware)

        budget_ratio = 0.9 if hardware["vram_gb"] else 0.65
        practical_budget = capacity_gb * budget_ratio
        if required_ram_gb <= practical_budget:
            return self._assessment("blue", "good", "Likely comfortable for this machine.", required_ram_gb, hardware)
        if required_ram_gb <= practical_budget * 1.25:
            return self._assessment("yellow", "tight", "Likely usable, but may be slow or memory-heavy.", required_ram_gb, hardware)
        return self._assessment("red", "heavy", "Likely too large for the detected local memory.", required_ram_gb, hardware)

    def _assessment(self, color, level, label, required_ram_gb, hardware):
        return {
            "color": color,
            "level": level,
            "label": label,
            "required_ram_gb": round(required_ram_gb, 1) if required_ram_gb else 0,
            "hardware": hardware,
        }

    def _estimate_required_ram_gb(self, entry):
        recommended = float(entry.get("recommended_ram_gb") or 0)
        if recommended:
            return recommended

        size_bytes = float(entry.get("size_bytes") or 0)
        if size_bytes:
            return (size_bytes / (1024 ** 3)) + 3

        params_b = self._extract_parameter_billions(entry)
        if not params_b:
            return 0

        quantization = str(entry.get("quantization") or entry.get("filename") or "").lower()
        bytes_per_param = 0.7
        if "q8" in quantization:
            bytes_per_param = 1.1
        elif "q6" in quantization:
            bytes_per_param = 0.85
        elif "q3" in quantization:
            bytes_per_param = 0.55
        return params_b * bytes_per_param + 3

    def _extract_parameter_billions(self, entry):
        value = " ".join(
            str(entry.get(key) or "")
            for key in ("display_name", "description", "filename", "catalog_key")
        )
        match = re.search(r"(\d+(?:\.\d+)?)\s*b\b", value, flags=re.IGNORECASE)
        return float(match.group(1)) if match else 0

    def _get_total_ram_gb(self):
        if hasattr(os, "sysconf"):
            try:
                pages = os.sysconf("SC_PHYS_PAGES")
                page_size = os.sysconf("SC_PAGE_SIZE")
                return round((pages * page_size) / (1024 ** 3), 1)
            except (OSError, ValueError):
                pass
        return 0

    def _get_nvidia_vram_gb(self):
        if not shutil.which("nvidia-smi"):
            return 0
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
        except (OSError, subprocess.TimeoutExpired):
            return 0
        values = []
        for line in result.stdout.splitlines():
            try:
                values.append(float(line.strip()) / 1024)
            except ValueError:
                continue
        return round(max(values), 1) if values else 0

    def _estimate_gpu_layers_for_vram(self, model_path, vram_gb):
        model_file = Path(model_path)
        try:
            model_size_bytes = model_file.stat().st_size
        except OSError:
            return None

        block_count = self._read_model_block_count(model_file)
        if block_count <= 0 or model_size_bytes <= 0:
            return -1

        available_bytes = vram_gb * self.GPU_MEMORY_SAFETY_RATIO * (1024 ** 3)
        overhead_bytes = model_size_bytes * self.MODEL_NON_LAYER_OVERHEAD_RATIO
        layer_budget_bytes = max(0, available_bytes - overhead_bytes)
        bytes_per_layer = max(1, (model_size_bytes - overhead_bytes) / block_count)
        estimated_layers = int(layer_budget_bytes // bytes_per_layer)

        if estimated_layers >= block_count:
            return -1

        return max(0, estimated_layers)

    def _read_model_block_count(self, model_path):
        try:
            architecture_metadata = read_gguf_metadata(
                model_path,
                keys=("general.architecture",),
            )
        except (GgufMetadataError, OSError):
            return 0

        architecture = str(architecture_metadata.get("general.architecture") or "").strip()
        if not architecture:
            return 0

        try:
            block_metadata = read_gguf_metadata(
                model_path,
                keys=(f"{architecture}.block_count",),
            )
        except (GgufMetadataError, OSError):
            return 0

        try:
            return int(block_metadata.get(f"{architecture}.block_count") or 0)
        except (TypeError, ValueError):
            return 0
