"""Parameter definitions and CPU family capability checks"""
import os
import re

# Settings parameters list
SETTINGS_PARAMS = [
    # Power limits (values from ryzenadj -i are in W; CLI takes mW)
    {
        "param": "stapm-limit",
        "label": "STAPM Limit",
        "desc": "Sustained Power Limit (STAPM)",
        "min": 5000, "max": 130000, "step": 1000,
        "unit": "mW", "display_divisor": 1000, "display_unit": "W",
        "category": "power",
        "value_key": "STAPM LIMIT",
    },
    {
        "param": "fast-limit",
        "label": "PPT Fast Limit",
        "desc": "Actual Power Limit (PPT FAST)",
        "min": 5000, "max": 130000, "step": 1000,
        "unit": "mW", "display_divisor": 1000, "display_unit": "W",
        "category": "power",
        "value_key": "PPT LIMIT FAST",
    },
    {
        "param": "slow-limit",
        "label": "PPT Slow Limit",
        "desc": "Average Power Limit (PPT SLOW)",
        "min": 5000, "max": 130000, "step": 1000,
        "unit": "mW", "display_divisor": 1000, "display_unit": "W",
        "category": "power",
        "value_key": "PPT LIMIT SLOW",
    },
    {
        "param": "apu-slow-limit",
        "label": "APU PPT Slow Limit",
        "desc": "APU PPT Slow limit (A+A dGPU platforms)",
        "min": 5000, "max": 130000, "step": 1000,
        "unit": "mW", "display_divisor": 1000, "display_unit": "W",
        "category": "power",
        "value_key": "PPT LIMIT APU",
    },
    # Current limits (values from ryzenadj -i are in A; CLI takes mA)
    {
        "param": "vrm-current",
        "label": "VRM VDD Current (TDC)",
        "desc": "TDC Limit VDD - VRM Current",
        "min": 10000, "max": 300000, "step": 1000,
        "unit": "mA", "display_divisor": 1000, "display_unit": "A",
        "category": "current",
        "value_key": "TDC LIMIT VDD",
    },
    {
        "param": "vrmsoc-current",
        "label": "VRM SoC Current (TDC)",
        "desc": "TDC Limit SoC - VRM SoC Current",
        "min": 10000, "max": 100000, "step": 1000,
        "unit": "mA", "display_divisor": 1000, "display_unit": "A",
        "category": "current",
        "value_key": "TDC LIMIT SOC",
    },
    {
        "param": "vrmmax-current",
        "label": "VRM VDD Max Current (EDC)",
        "desc": "EDC Limit VDD - VRM Maximum Current",
        "min": 10000, "max": 300000, "step": 1000,
        "unit": "mA", "display_divisor": 1000, "display_unit": "A",
        "category": "current",
        "value_key": "EDC LIMIT VDD",
    },
    {
        "param": "vrmsocmax-current",
        "label": "VRM SoC Max Current (EDC)",
        "desc": "EDC Limit SoC - VRM SoC Maximum Current",
        "min": 10000, "max": 100000, "step": 1000,
        "unit": "mA", "display_divisor": 1000, "display_unit": "A",
        "category": "current",
        "value_key": "EDC LIMIT SOC",
    },
    {
        "param": "psi0-current",
        "label": "PSI0 VDD Current",
        "desc": "PSI0 VDD Current Limit",
        "min": 1000, "max": 50000, "step": 1000,
        "unit": "mA", "display_divisor": 1000, "display_unit": "A",
        "category": "current",
        "value_key": "PSI0 CURRENT VDD",
    },
    {
        "param": "psi3cpu_current",
        "label": "PSI3 CPU Current",
        "desc": "PSI3 CPU Current Limit",
        "min": 1000, "max": 50000, "step": 1000,
        "unit": "mA", "display_divisor": 1000, "display_unit": "A",
        "category": "current",
        "value_key": "PSI3 CURRENT CPU",
    },
    {
        "param": "psi0soc-current",
        "label": "PSI0 SoC Current",
        "desc": "PSI0 SoC Current Limit",
        "min": 1000, "max": 50000, "step": 1000,
        "unit": "mA", "display_divisor": 1000, "display_unit": "A",
        "category": "current",
        "value_key": "PSI0 CURRENT SOC",
    },
    {
        "param": "psi3gfx_current",
        "label": "PSI3 GFX Current",
        "desc": "PSI3 GFX Current Limit",
        "min": 1000, "max": 50000, "step": 1000,
        "unit": "mA", "display_divisor": 1000, "display_unit": "A",
        "category": "current",
        "value_key": "PSI3 CURRENT GFX",
        "is_gpu": True,
    },
    # Thermal limits
    {
        "param": "tctl-temp",
        "label": "Tctl Temperature Limit",
        "desc": "CPU die temperature ceiling",
        "min": 40, "max": 105, "step": 1,
        "unit": "°C", "display_divisor": 1, "display_unit": "°C",
        "category": "thermal",
        "value_key": "THM LIMIT CORE",
    },
    {
        "param": "apu-skin-temp",
        "label": "APU Skin Temp Limit",
        "desc": "STT Limit APU - skin temperature",
        "min": 20, "max": 100, "step": 1,
        "unit": "°C", "display_divisor": 1, "display_unit": "°C",
        "category": "thermal",
        "value_key": "STT LIMIT APU",
    },
    {
        "param": "dgpu-skin-temp",
        "label": "dGPU Skin Temp Limit",
        "desc": "STT Limit dGPU - discrete GPU skin temperature",
        "min": 0, "max": 100, "step": 1,
        "unit": "°C", "display_divisor": 1, "display_unit": "°C",
        "category": "thermal",
        "value_key": "STT LIMIT dGPU",
    },
    {
        "param": "skin-temp-limit",
        "label": "Skin Temp Power Limit",
        "desc": "Skin Temperature Power Limit (controls power envelope when skin threshold reached)",
        "min": 5000, "max": 130000, "step": 1000,
        "unit": "mW", "display_divisor": 1000, "display_unit": "W",
        "category": "thermal",
        "value_key": "SkinTempLimit",
    },
    # Timing
    {
        "param": "stapm-time",
        "label": "STAPM Constant Time",
        "desc": "STAPM time constant (seconds)",
        "min": 0, "max": 1000, "step": 10,
        "unit": "s", "display_divisor": 1, "display_unit": "s",
        "category": "timing",
        "value_key": "StapmTimeConst",
    },
    {
        "param": "slow-time",
        "label": "Slow PPT Time Constant",
        "desc": "Slow PPT time constant (seconds)",
        "min": 0, "max": 1000, "step": 10,
        "unit": "s", "display_divisor": 1, "display_unit": "s",
        "category": "timing",
        "value_key": "SlowPPTTimeConst",
    },
    # GPU Options
    {
        "param": "max-gfxclk",
        "label": "Max iGPU Clock",
        "desc": "Maximum graphics core clock frequency ceiling",
        "min": 400, "max": 3500, "step": 50,
        "unit": "MHz", "display_divisor": 1, "display_unit": "MHz",
        "category": "clocks",
        "value_key": "GFX CLK LIMIT (MAX)",
        "is_gpu": True,
    },
    {
        "param": "min-gfxclk",
        "label": "Min iGPU Clock",
        "desc": "Minimum graphics core clock frequency floor",
        "min": 400, "max": 3500, "step": 50,
        "unit": "MHz", "display_divisor": 1, "display_unit": "MHz",
        "category": "clocks",
        "value_key": "GFX CLK LIMIT (MIN)",
        "is_gpu": True,
    },
    {
        "param": "vrmgfx-current",
        "label": "VRM iGPU Current (TDC)",
        "desc": "TDC Limit GFX - graphics VRM current limit",
        "min": 10000, "max": 150000, "step": 1000,
        "unit": "mA", "display_divisor": 1000, "display_unit": "A",
        "category": "current",
        "value_key": "TDC LIMIT GFX",
        "is_gpu": True,
    },
    {
        "param": "vrmgfxmax_current",
        "label": "VRM iGPU Max Current (EDC)",
        "desc": "EDC Limit GFX - graphics VRM maximum peak current",
        "min": 10000, "max": 180000, "step": 1000,
        "unit": "mA", "display_divisor": 1000, "display_unit": "A",
        "category": "current",
        "value_key": "EDC LIMIT GFX",
        "is_gpu": True,
    },
    # CPU Options
    {
        "param": "oc-clk",
        "label": "CPU Manual Overclock Clock",
        "desc": "Forced manual CPU core frequency (Enables OC mode)",
        "min": 1000, "max": 6000, "step": 25,
        "unit": "MHz", "display_divisor": 1, "display_unit": "MHz",
        "category": "clocks",
        "value_key": "CPU OC CLK",
        "is_cpu": True,
    },
    {
        "param": "oc-volt",
        "label": "CPU Manual Overclock Voltage",
        "desc": "Forced manual CPU core voltage (Enables OC mode)",
        "min": 700, "max": 1500, "step": 5,
        "unit": "mV", "display_divisor": 1, "display_unit": "mV",
        "category": "current",
        "value_key": "CPU OC VOLT",
        "is_cpu": True,
    },

    # GFX Forced Clock
    {
        "param": "gfx-clk",
        "label": "Forced iGPU Clock",
        "desc": "Force graphics core clock speed (Renoir Only)",
        "min": 400, "max": 3000, "step": 25,
        "unit": "MHz", "display_divisor": 1, "display_unit": "MHz",
        "category": "clocks",
        "value_key": "GFX FORCED CLK",
        "is_gpu": True,
    },
    # SoC Clock Limits
    {
        "param": "max-socclk-frequency",
        "label": "Max SoC Clock",
        "desc": "Maximum System-on-Chip (SoC) clock speed",
        "min": 400, "max": 2000, "step": 33,
        "unit": "MHz", "display_divisor": 1, "display_unit": "MHz",
        "category": "clocks",
        "value_key": "SOCCLK LIMIT (MAX)",
        "is_cpu": True,
    },
    {
        "param": "min-socclk-frequency",
        "label": "Min SoC Clock",
        "desc": "Minimum System-on-Chip (SoC) clock speed",
        "min": 400, "max": 2000, "step": 33,
        "unit": "MHz", "display_divisor": 1, "display_unit": "MHz",
        "category": "clocks",
        "value_key": "SOCCLK LIMIT (MIN)",
        "is_cpu": True,
    },
    # FCLK Limits
    {
        "param": "max-fclk-frequency",
        "label": "Max FCLK",
        "desc": "Maximum Transmission (CPU-GPU) Frequency",
        "min": 400, "max": 3000, "step": 33,
        "unit": "MHz", "display_divisor": 1, "display_unit": "MHz",
        "category": "clocks",
        "value_key": "FCLK LIMIT (MAX)",
        "is_cpu": True,
    },
    {
        "param": "min-fclk-frequency",
        "label": "Min FCLK",
        "desc": "Minimum Transmission (CPU-GPU) Frequency",
        "min": 400, "max": 3000, "step": 33,
        "unit": "MHz", "display_divisor": 1, "display_unit": "MHz",
        "category": "clocks",
        "value_key": "FCLK LIMIT (MIN)",
        "is_cpu": True,
    },
    # VCN Limits
    {
        "param": "max-vcn",
        "label": "Max VCN",
        "desc": "Maximum Video Core Next Frequency",
        "min": 400, "max": 3000, "step": 33,
        "unit": "MHz", "display_divisor": 1, "display_unit": "MHz",
        "category": "clocks",
        "value_key": "VCN LIMIT (MAX)",
        "is_gpu": True,
    },
    {
        "param": "min-vcn",
        "label": "Min VCN",
        "desc": "Minimum Video Core Next Frequency",
        "min": 400, "max": 3000, "step": 33,
        "unit": "MHz", "display_divisor": 1, "display_unit": "MHz",
        "category": "clocks",
        "value_key": "VCN LIMIT (MIN)",
        "is_gpu": True,
    },
    # LCLK Limits
    {
        "param": "max-lclk",
        "label": "Max LCLK",
        "desc": "Maximum Data Launch Clock",
        "min": 400, "max": 3000, "step": 33,
        "unit": "MHz", "display_divisor": 1, "display_unit": "MHz",
        "category": "clocks",
        "value_key": "LCLK LIMIT (MAX)",
        "is_cpu": True,
    },
    {
        "param": "min-lclk",
        "label": "Min LCLK",
        "desc": "Minimum Data Launch Clock",
        "min": 400, "max": 3000, "step": 33,
        "unit": "MHz", "display_divisor": 1, "display_unit": "MHz",
        "category": "clocks",
        "value_key": "LCLK LIMIT (MIN)",
        "is_cpu": True,
    },

    # VRM CVIP Current Limit
    {
        "param": "vrmcvip-current",
        "label": "VRM CVIP Current (TDC)",
        "desc": "TDC Limit CVIP - processor fabric current limit",
        "min": 5000, "max": 100000, "step": 1000,
        "unit": "mA", "display_divisor": 1000, "display_unit": "A",
        "category": "current",
        "value_key": "TDC LIMIT CVIP",
        "is_cpu": True,
    },
    # PROCHOT Ramp Time
    {
        "param": "prochot-deassertion-ramp",
        "label": "PROCHOT Deassertion Ramp",
        "desc": "Ramp time after processor hot signal is deasserted",
        "min": 0, "max": 5000, "step": 100,
        "unit": "ms", "display_divisor": 1, "display_unit": "ms",
        "category": "timing",
        "value_key": "PROCHOT Ramp",
    },
]


def _get_physical_core_count() -> int:
    """Count physical CPU cores on the system (read from topology sysfs)"""
    try:
        cores = set()
        for i in range(os.cpu_count() or 1):
            path = f'/sys/devices/system/cpu/cpu{i}/topology/core_cpus_list'
            if os.path.exists(path):
                with open(path) as f:
                    cores.add(f.read().strip())
        if cores:
            return len(cores)
    except Exception:
        pass
    count = os.cpu_count()
    return count if count else 8


# Add Curve Optimizer options to list
SETTINGS_PARAMS.append({
    "param": "set-coall",
    "label": "All Cores Offset",
    "desc": "Curve Optimizer offset applied to all CPU cores",
    "min": -30, "max": 30, "step": 1,
    "unit": "", "display_divisor": 1, "display_unit": "",
    "category": "undervolt",
    "value_key": "COALL",
    "default": 0,
    "is_cpu": True
})

SETTINGS_PARAMS.append({
    "param": "set-cogfx",
    "label": "iGPU Offset",
    "desc": "Curve Optimizer offset applied to the graphics core",
    "min": -30, "max": 30, "step": 1,
    "unit": "", "display_divisor": 1, "display_unit": "",
    "category": "undervolt",
    "value_key": "COGFX",
    "default": 0,
    "is_gpu": True
})

for i in range(_get_physical_core_count()):
    SETTINGS_PARAMS.append({
        "param": f"set-coper-{i}",
        "label": f"Core {i} Offset",
        "desc": f"Curve Optimizer offset for Core {i}",
        "min": -30, "max": 30, "step": 1,
        "unit": "", "display_divisor": 1, "display_unit": "",
        "category": "undervolt",
        "value_key": f"COPER_{i}",
        "default": 0,
        "is_cpu": True
    })


def _is_mobile_or_apu(cpu_family: str) -> bool:
    """Check if CPU is a laptop or APU chip (kind of researched cpu models for this list)"""
    fam_lower = cpu_family.lower()
    apu_families = {
        "strix", "phoenix", "hawk", "rembrandt", "barcelo", "cezanne",
        "lucienne", "renoir", "picasso", "raven", "mendocino", "sabin",
        "kraken", "krackan", "sonoma", "dragon", "fire", "dali", "pollock",
        "vangogh", "aerith", "sephiroth"
    }
    if any(fam in fam_lower for fam in apu_families):
        return True

    try:
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if line.strip().startswith("model name"):
                    model_name = line.split(":", 1)[1].strip().lower()
                    if "ryzen" in model_name:
                        if (
                            " ai " in model_name or
                            " z1 " in model_name or
                            " z1 extreme" in model_name or
                            any(suffix in model_name for suffix in ["370", "365", "375"])
                        ):
                            return True
                        if re.search(r"\b\d{3,4}(u|h|hs|hx|g|ge)\b", model_name):
                            return True
    except Exception:
        pass
    return False


def _is_zen3_or_newer() -> bool:
    """Check if the CPU is Zen 3 or newer (Family 25 or higher in cpuinfo)"""
    try:
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if line.strip().startswith("cpu family"):
                    family_val = int(line.split(":", 1)[1].strip())
                    return family_val >= 25
    except Exception:
        pass
    return True


def is_sysfs_gfx_clk_available() -> bool:
    """Check if AMD GPU overdrive is available in sysfs"""
    for i in range(4):
        if os.path.exists(f"/sys/class/drm/card{i}/device/pp_od_clk_voltage"):
            return True
    return False


def is_parameter_supported(param: str, cpu_family: str, supported_params: set[str]) -> bool:
    """Check if a parameter is supported on this CPU model"""
    if param.startswith("set-co"):
        if not _is_zen3_or_newer():
            return False
        if param == "set-cogfx":
            fam_lower = cpu_family.lower()
            if "strix" in fam_lower or "phoenix" in fam_lower or "hawk" in fam_lower:
                return False
            try:
                with open("/proc/cpuinfo", "r") as f:
                    for line in f:
                        if line.strip().startswith("model name"):
                            model_name = line.split(":", 1)[1].strip().lower()
                            if "370" in model_name or "365" in model_name or "375" in model_name:
                                return False
            except Exception:
                pass
        return True

    if param in ("skin-temp-limit", "apu-skin-temp"):
        if param == "apu-skin-temp":
            fam_lower = cpu_family.lower()
            if "strix" in fam_lower or "phoenix" in fam_lower or "hawk" in fam_lower:
                return False
            try:
                with open("/proc/cpuinfo", "r") as f:
                    for line in f:
                        if line.strip().startswith("model name"):
                            model_name = line.split(":", 1)[1].strip().lower()
                            if "370" in model_name or "365" in model_name or "375" in model_name:
                                return False
            except Exception:
                pass
        if _is_mobile_or_apu(cpu_family):
            return True

    if param == "dgpu-skin-temp":
        fam_lower = cpu_family.lower()
        if "strix" in fam_lower or "phoenix" in fam_lower or "hawk" in fam_lower:
            return False

    if supported_params and param in supported_params:
        return True

    if param in ("oc-clk", "oc-volt"):
        fam_lower = cpu_family.lower()
        is_unlocked_hx = False
        try:
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if line.strip().startswith("model name"):
                        model_name = line.split(":", 1)[1].strip().lower()
                        if ("hx" in model_name or "hk" in model_name) and "ai " not in model_name:
                            is_unlocked_hx = True
                            break
        except Exception:
            pass
        return is_unlocked_hx

    if param in ("min-gfxclk", "max-gfxclk"):
        return (supported_params and param in supported_params) or is_sysfs_gfx_clk_available()

    if param == "gfx-clk":
        igpu_indicators = {"gfx-clk", "gfx-clock", "max-gfxclk", "min-gfxclk", "vrmgfx-current", "vrmgfxmax_current"}
        if supported_params and any(ind in supported_params for ind in igpu_indicators):
            return True
        if _is_mobile_or_apu(cpu_family):
            return True

    return False
