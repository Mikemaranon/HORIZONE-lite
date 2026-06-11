import os
import platform
import re
import shutil
import subprocess


class LocalHardwareProfile:
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
            "memory_kind": "unified" if is_apple_silicon else ("vram" if vram_gb else "system"),
        }

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
