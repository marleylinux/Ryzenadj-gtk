"""Backend logic for interacting with ryzenadj and system settings"""
import os
import re
import json
import logging
import shutil
import time

# Import settings and parameters from other modules (re-export many for the ryzen.* facade used by the rest of the app)
from params import (
    SETTINGS_PARAMS,
    is_parameter_supported
)
from system import (
    is_on_ac_power,
    check_system_lockdown_status,
    get_live_cpu_clock,
    get_live_gpu_clock,
    is_sysfs_gfx_clk_available,
    get_sysfs_gfx_clk_hardware_range,
    get_sysfs_gfx_clk_limits,
    apply_gfx_clk_sysfs
)
from settings import (
    CONFIG_FILE,
    PROFILES_FILE,
    SYSTEM_CONFIG_DIR,
    SYSTEM_CONFIG_FILE,
    SUDOERS_DROP_IN,
    _run_elevated,
    _hardware_lock,
    load_settings,
    save_settings,
    remove_setting_from_startup,
    remove_settings_from_startup,
    is_service_enabled,
    sync_system_settings,
    set_service_enabled,
    factory_reset,
    load_profiles,
    save_profiles
)

log = logging.getLogger(__name__)


def is_ryzenadj_installed() -> bool:
    """Check if ryzenadj command is installed on the system"""
    return shutil.which("ryzenadj") is not None


def get_current_info() -> dict:
    """Get active telemetry values from ryzenadj (researched how ryzenadj outputs table metrics)"""
    metrics = {}
    supported = set()
    try:
        res = _run_elevated(
            ["ryzenadj", "-i"],
            capture_output=True, text=True, timeout=10
        )
        if res.returncode == 0:
            metrics = _parse_info_output(res.stdout)
            supported = _parse_supported_params(res.stdout)
        else:
            log.debug("ryzenadj -i (refresh) failed: %s", res.stderr)
    except Exception as e:
        log.debug("Error running ryzenadj -i (refresh): %s", e)

    gpu_clk = get_live_gpu_clock()
    if gpu_clk is not None:
        metrics["GFX FORCED CLK"] = gpu_clk

    sysfs_min, sysfs_max = get_sysfs_gfx_clk_limits()
    if "GFX CLK LIMIT (MAX)" not in metrics and sysfs_max is not None:
        metrics["GFX CLK LIMIT (MAX)"] = sysfs_max
    if "GFX CLK LIMIT (MIN)" not in metrics and sysfs_min is not None:
        metrics["GFX CLK LIMIT (MIN)"] = sysfs_min

    oc_supported = "oc-clk" in supported if supported else False
    if oc_supported:
        cpu_clk = get_live_cpu_clock()
        if cpu_clk is not None:
            metrics["CPU OC CLK"] = cpu_clk

    return metrics


def _parse_cpu_family(stdout: str) -> str:
    """Get CPU Family name from ryzenadj logs"""
    for line in stdout.splitlines():
        if line.startswith("CPU Family:"):
            return line.split(":", 1)[1].strip()
    return "Unknown"


def _parse_supported_params(stdout: str) -> set[str]:
    """Parse supported parameters list from ryzenadj output"""
    supported = set()
    pattern = re.compile(
        r"\|\s*(.+?)\s*\|\s*([\d\.\-]+)\s*\|\s*(.*?)\s*\|"
    )
    for line in stdout.splitlines():
        m = pattern.match(line.strip())
        if m:
            param = m.group(3).strip()
            if param:
                for p in re.split(r"\s*/\s*|\s+", param):
                    supported.add(p)
    return supported


def _parse_info_output(output: str) -> dict:
    """Extract metrics from ryzenadj table (used research to build the regex matching for lines)"""
    metrics = {}
    pattern = re.compile(
        r"\|\s*(.+?)\s*\|\s*([\d\.\-]+)\s*\|\s*(.*?)\s*\|"
    )
    for line in output.splitlines():
        m = pattern.match(line.strip())
        if m:
            name = m.group(1).strip()
            try:
                value = float(m.group(2).strip())
            except ValueError:
                continue
            metrics[name] = value
    return metrics


def get_cpu_family() -> str:
    """Get CPU family string from ryzenadj"""
    try:
        res = _run_elevated(
            ["ryzenadj", "-i"],
            capture_output=True, text=True, timeout=10
        )
        if res.returncode == 0:
            return _parse_cpu_family(res.stdout)
    except Exception:
        pass
    return "Unknown"


def get_supported_parameters() -> set[str]:
    """Get list of parameters ryzenadj supports"""
    try:
        res = _run_elevated(
            ["ryzenadj", "-i"],
            capture_output=True, text=True, timeout=10
        )
        if res.returncode == 0:
            return _parse_supported_params(res.stdout)
    except Exception as e:
        log.error("Error getting supported parameters: %s", e)
    return set()


def get_initial_data() -> tuple[str, dict, set, bool]:
    """Get CPU info and support metrics on startup"""
    try:
        res = _run_elevated(["ryzenadj", "-i"], capture_output=True, text=True, timeout=15)
        
        if res.returncode != 0 and ("password is required" in res.stderr.lower() or "sudo:" in res.stderr.lower()):
            log.error("Authentication failed: ryzenadj requires root access.")
            return "Unknown", {}, set(), False

        cpu_family = _parse_cpu_family(res.stdout)
        info_dict = _parse_info_output(res.stdout)
        supported = _parse_supported_params(res.stdout)
        return cpu_family, info_dict, supported, True
    except Exception as e:
        log.error("Error getting initial data: %s", e)
        return "Unknown", {}, set(), False


def _build_ryzenadj_args(settings: dict) -> list[str]:
    """Build ryzenadj CLI arguments (researched how ryzenadj encodes Curve Optimizer offsets)"""
    args = []
    enable_oc = False
    for param in settings:
        if param in ("oc-clk", "oc-volt"):
            enable_oc = True
            break
    if enable_oc:
        args.append("--enable-oc")

    for param, value in settings.items():
        val_int = int(value)
        if param == "set-coall":
            val_int = max(-30, min(30, val_int))
            encoded = (0x100000 - abs(val_int)) if val_int < 0 else val_int
            args.append(f"--set-coall={encoded}")
        elif param == "set-cogfx":
            val_int = max(-30, min(30, val_int))
            encoded = (0x100000 - abs(val_int)) if val_int < 0 else val_int
            args.append(f"--set-cogfx={encoded}")
        elif param.startswith("set-coper-"):
            core_idx = int(param.split("-")[-1])
            val_int = max(-30, min(30, val_int))
            if val_int < 0:
                encoded = (core_idx << 20) | (0x100000 - abs(val_int))
            else:
                encoded = (core_idx << 20) | val_int
            args.append(f"--set-coper={encoded}")
        elif param == "oc-volt":
            volts = val_int / 1000.0
            vid = max(0, min(127, int((1.55 - volts) / 0.00625)))
            args.append(f"--oc-volt={vid}")
        else:
            args.append(f"--{param}={val_int}")
    return args


def apply_settings(settings: dict, supported_params: set[str] = None, cpu_family: str = None, save: bool = True) -> tuple[bool, str]:
    """Apply settings to hardware using ryzenadj or sysfs fallback (checks which parameters are natively supported)"""
    if not settings:
        return False, "No settings to apply."

    valid_param_names = {m["param"] for m in SETTINGS_PARAMS}
    unknown = [p for p in settings if p not in valid_param_names]
    if unknown:
        log.warning("apply_settings: ignoring unknown/unexpected params: %s", unknown)
        settings = {k: v for k, v in settings.items() if k in valid_param_names}

    if supported_params is None:
        supported_params = get_supported_parameters()

    if cpu_family is None:
        cpu_family = get_cpu_family()

    unsupported = [p for p in settings if not is_parameter_supported(p, cpu_family, supported_params)]
    if unsupported:
        log.info("apply_settings: filtering out unsupported params: %s", unsupported)
        settings = {k: v for k, v in settings.items() if is_parameter_supported(k, cpu_family, supported_params)}

    if not settings:
        return False, "No valid settings to apply after filtering unsupported params."

    GFX_CLK_PARAMS = ("min-gfxclk", "max-gfxclk")
    ryzenadj_native = {"min-gfxclk", "max-gfxclk"} & set(supported_params or [])
    sysfs_clk_settings = {
        p: v for p, v in settings.items()
        if p in GFX_CLK_PARAMS and p not in ryzenadj_native
    }
    ryzenadj_settings = {k: v for k, v in settings.items() if k not in sysfs_clk_settings}

    sysfs_ok = True
    sysfs_msg = ""
    if sysfs_clk_settings:
        min_val = sysfs_clk_settings.get("min-gfxclk")
        max_val = sysfs_clk_settings.get("max-gfxclk")
        sysfs_ok, sysfs_msg = apply_gfx_clk_sysfs(
            int(min_val) if min_val is not None else None,
            int(max_val) if max_val is not None else None,
        )
        if sysfs_ok:
            log.info("sysfs GFX clk fallback applied: %s", sysfs_clk_settings)
        else:
            log.error("sysfs GFX clk fallback failed: %s", sysfs_msg)

    ryzenadj_ok = True
    ryzenadj_msg = ""
    if ryzenadj_settings:
        cmd = ["ryzenadj"] + _build_ryzenadj_args(ryzenadj_settings)
        print(f"\n[Ryzenadj-gtk] Executing hardware write command:\n  {' '.join(cmd)}\n", flush=True)
        try:
            res = _run_elevated(cmd, capture_output=True, text=True, timeout=15)
            if res.returncode != 0:
                err = (res.stderr or "") + "\n" + (res.stdout or "")
                lines = [
                    line for line in err.splitlines()
                    if "ryzen_smu" not in line and "Ryzen SMU" not in line
                    and "Executing" not in line and "PrepareForSleep" not in line
                ]
                ryzenadj_msg = "\n".join(lines).strip() or "ryzenadj returned error"
                ryzenadj_ok = False
        except Exception as e:
            ryzenadj_ok = False
            ryzenadj_msg = str(e)

    overall_ok = (ryzenadj_ok or not ryzenadj_settings) and (sysfs_ok or not sysfs_clk_settings)
    if overall_ok:
        if save:
            current_saved = load_settings()
            valid_applied = {
                k: v for k, v in settings.items()
                if is_parameter_supported(k, cpu_family, supported_params)
            }
            current_saved.update(valid_applied)
            save_settings(current_saved)
            if is_service_enabled():
                if not sync_system_settings(current_saved):
                    return True, "Settings applied, but failed to update boot configuration (/etc/ryzenadj-gtk/settings.json)."
        return True, "Settings applied successfully."
    else:
        msgs = [m for m in (ryzenadj_msg, sysfs_msg) if m]
        return False, "\n".join(msgs)


def apply_preset(preset_name: str) -> tuple[bool, str]:
    """Apply one of the default ryzenadj power presets"""
    if preset_name == "power-saving":
        cmd = ["ryzenadj", "--power-saving"]
    elif preset_name == "max-performance":
        cmd = ["ryzenadj", "--max-performance"]
    else:
        return False, f"Unknown preset: {preset_name}"
    print(f"\n[Ryzenadj-gtk] Executing preset command:\n  {' '.join(cmd)}\n", flush=True)
    try:
        res = _run_elevated(cmd, capture_output=True, text=True, timeout=15)
        if res.returncode != 0:
            err = res.stderr or ""
            lines = [line for line in err.splitlines() if "ryzen_smu" not in line and "Ryzen SMU" not in line]
            cleaned_err = "\n".join(lines).strip()
            return False, cleaned_err or "ryzenadj returned error"
        return True, f"Preset '{preset_name}' applied."
    except Exception as e:
        return False, str(e)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--apply-saved":
        if os.path.exists(SYSTEM_CONFIG_FILE):
            try:
                with open(SYSTEM_CONFIG_FILE, "r") as f:
                    settings = json.load(f)
                if settings:
                    max_retries = 5
                    for attempt in range(1, max_retries + 1):
                        cpu_family, info, supported_params, auth_ok = get_initial_data()
                        if auth_ok:
                            ok, msg = apply_settings(settings, supported_params, cpu_family, save=False)
                            if ok:
                                print(f"Successfully applied ryzenadj and AMDGPU sysfs overdrive settings (attempt {attempt}).")
                                sys.exit(0)
                            else:
                                print(f"Attempt {attempt} failed to apply settings: {msg}")
                        else:
                            print(f"Attempt {attempt} failed: ryzenadj requires root/sudoers rules.")

                        if attempt < max_retries:
                            time.sleep(3)
                        else:
                            print("All boot apply attempts failed.")
                            sys.exit(1)
            except Exception as e:
                print(f"Failed to apply system settings: {e}")
                sys.exit(1)
        else:
            print("No system settings file found at " + SYSTEM_CONFIG_FILE)
            sys.exit(0)
