"""Sensors, hardware diagnostics, and AMDGPU interfaces"""
import os
import re
import shutil
import logging
import subprocess

log = logging.getLogger(__name__)


def is_on_ac_power() -> bool:
    """Check if the system is running on AC power"""
    has_mains = False
    try:
        for name in os.listdir("/sys/class/power_supply"):
            base = f"/sys/class/power_supply/{name}"
            type_path = f"{base}/type"
            if os.path.exists(type_path):
                try:
                    with open(type_path, "r") as f:
                        psu_type = f.read().strip().lower()
                    if psu_type != "mains":
                        continue
                except Exception:
                    continue
            else:
                name_lower = name.lower()
                if not (
                    name_lower.startswith("ac")
                    or name_lower.startswith("adp")
                    or "charger" in name_lower
                ):
                    continue
            has_mains = True
            online_path = f"{base}/online"
            if os.path.exists(online_path):
                try:
                    with open(online_path, "r") as f:
                        if f.read().strip() == "1":
                            return True
                except Exception:
                    pass
    except Exception as e:
        log.debug("Failed to check AC power supply: %s", e)
    return not has_mains


def check_system_lockdown_status() -> dict:
    """Check if Secure Boot or Kernel Lockdown is active"""
    status = {
        "secure_boot": False,
        "lockdown_active": False,
        "lockdown_mode": "none",
        "iomem_relaxed": True,
        "ryzen_smu_loaded": False
    }

    for path in [
        "/sys/firmware/efi/efivars/SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c/data",
        "/sys/firmware/efi/vars/SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c/data"
    ]:
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    data = f.read()
                    if data:
                        status["secure_boot"] = (data[-1] == 1)
                    break
            except Exception:
                pass

    lockdown_path = "/sys/kernel/security/lockdown"
    if os.path.exists(lockdown_path):
        try:
            with open(lockdown_path, "r") as f:
                content = f.read().strip()
                match = re.search(r"\[(.*?)\]", content)
                if match:
                    mode = match.group(1)
                    status["lockdown_mode"] = mode
                    if mode != "none":
                        status["lockdown_active"] = True
        except Exception:
            pass

    try:
        if os.path.exists("/proc/cmdline"):
            with open("/proc/cmdline", "r") as f:
                cmdline = f.read()
                status["iomem_relaxed"] = "iomem=relaxed" in cmdline
    except Exception:
        pass

    status["ryzen_smu_loaded"] = os.path.exists("/sys/module/ryzen_smu")
    return status


def get_live_cpu_clock() -> float | None:
    """Get current CPU average speed in MHz"""
    try:
        freqs = []
        base_dir = "/sys/devices/system/cpu"
        if os.path.exists(base_dir):
            for cpu in os.listdir(base_dir):
                if re.match(r"^cpu\d+$", cpu):
                    path = f"{base_dir}/{cpu}/cpufreq/scaling_cur_freq"
                    if os.path.exists(path):
                        with open(path, "r") as f:
                            khz = float(f.read().strip())
                            freqs.append(khz / 1000.0)
        if freqs:
            return sum(freqs) / len(freqs)
    except Exception:
        pass

    try:
        freqs = []
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if line.strip().startswith("cpu MHz"):
                    mhz = float(line.split(":", 1)[1].strip())
                    freqs.append(mhz)
        if freqs:
            return sum(freqs) / len(freqs)
    except Exception:
        pass
    return None


def get_live_gpu_clock() -> float | None:
    """Get current GPU speed in MHz"""
    try:
        for i in range(4):
            card = f"card{i}"
            base_dir = f"/sys/class/drm/{card}/device/hwmon"
            if os.path.exists(base_dir):
                for hwmon in os.listdir(base_dir):
                    freq_path = f"{base_dir}/{hwmon}/freq1_input"
                    if os.path.exists(freq_path):
                        with open(freq_path, "r") as f:
                            hz = float(f.read().strip())
                            return hz / 1_000_000.0
    except Exception:
        pass

    try:
        for i in range(4):
            card = f"card{i}"
            path = f"/sys/class/drm/{card}/device/pp_dpm_sclk"
            if os.path.exists(path):
                with open(path, "r") as f:
                    for line in f:
                        if "*" in line:
                            match = re.search(r"(\d+)\s*[mM]hz", line)
                            if match:
                                return float(match.group(1))
    except Exception:
        pass
    return None


def _find_amdgpu_od_card() -> str | None:
    """Find the active AMD GPU directory in sysfs"""
    for i in range(4):
        base = f"/sys/class/drm/card{i}/device"
        if os.path.exists(f"{base}/pp_od_clk_voltage"):
            return base
    return None


def is_sysfs_gfx_clk_available() -> bool:
    """Check if GPU clock controls are available in sysfs"""
    return _find_amdgpu_od_card() is not None


def get_sysfs_gfx_clk_hardware_range() -> tuple[int, int]:
    """Get hardware supported graphics clock range (researched how pp_od_clk_voltage formats ranges)"""
    base = _find_amdgpu_od_card()
    default_range = (200, 2700)
    if not base:
        return default_range
    try:
        with open(f"{base}/pp_od_clk_voltage", "r") as f:
            content = f.read()
        in_range = False
        for line in content.splitlines():
            line = line.strip()
            if line == "OD_RANGE:":
                in_range = True
                continue
            if line.startswith("OD_") and line != "OD_RANGE:":
                in_range = False
            if in_range:
                if line.startswith("SCLK:"):
                    parts = re.findall(r"(\d+)[Mm][Hh]z", line)
                    if len(parts) >= 2:
                        return int(parts[0]), int(parts[1])
        return default_range
    except Exception as e:
        log.debug("Failed to read sysfs GFX hardware range: %s", e)
        return default_range


def get_sysfs_gfx_clk_limits() -> tuple[float | None, float | None]:
    """Get current graphics clock limits from sysfs (kind of complex parsing here but it extracts the active speeds)"""
    base = _find_amdgpu_od_card()
    if not base:
        return None, None
    try:
        with open(f"{base}/pp_od_clk_voltage", "r") as f:
            content = f.read()
        min_mhz: float | None = None
        max_mhz: float | None = None
        in_sclk = False
        for line in content.splitlines():
            line = line.strip()
            if line == "OD_SCLK:":
                in_sclk = True
                continue
            if line.startswith("OD_"):
                in_sclk = False
            if in_sclk:
                m = re.match(r"(\d+):\s+(\d+)[Mm][Hh]z", line)
                if m:
                    level, mhz = int(m.group(1)), float(m.group(2))
                    if level == 0:
                        min_mhz = mhz
                    elif level == 1:
                        max_mhz = mhz
        return min_mhz, max_mhz
    except Exception as e:
        log.debug("Failed to read sysfs GFX clock limits: %s", e)
        return None, None


def _sysfs_tee_write(path: str, data: str) -> bool:
    """Write data to a sysfs path using sudo tee (needed to get past root restrictions)"""
    try:
        tee_path = shutil.which("tee") or "tee"
        res = subprocess.run(
            ["sudo", "-n", tee_path, path],
            input=data,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return res.returncode == 0
    except Exception as e:
        log.debug("sysfs tee write failed (%s): %s", path, e)
        return False


def apply_gfx_clk_sysfs(min_mhz: int | None, max_mhz: int | None) -> tuple[bool, str]:
    """Apply min and max GPU clock limits through sysfs (researched how manual DPM overrides work)"""
    base = _find_amdgpu_od_card()
    if not base:
        return False, "No AMD GPU with pp_od_clk_voltage support found in sysfs."

    od_path   = f"{base}/pp_od_clk_voltage"
    perf_path = f"{base}/power_dpm_force_performance_level"

    if not _sysfs_tee_write(perf_path, "manual"):
        return False, (
            "Failed to set power_dpm_force_performance_level to 'manual'.\n"
            "Make sure the tee sudoers rules are installed (re-run install.sh)."
        )

    if min_mhz is not None:
        if not _sysfs_tee_write(od_path, f"s 0 {int(min_mhz)}"):
            return False, f"Failed to write min GFX clock ({int(min_mhz)} MHz) to sysfs."

    if max_mhz is not None:
        if not _sysfs_tee_write(od_path, f"s 1 {int(max_mhz)}"):
            return False, f"Failed to write max GFX clock ({int(max_mhz)} MHz) to sysfs."

    if not _sysfs_tee_write(od_path, "c"):
        return False, "Failed to commit GFX clock changes via sysfs."

    parts = []
    if min_mhz is not None:
        parts.append(f"min {int(min_mhz)} MHz")
    if max_mhz is not None:
        parts.append(f"max {int(max_mhz)} MHz")
    return True, f"iGPU clock limits set via sysfs: {', '.join(parts)}."
