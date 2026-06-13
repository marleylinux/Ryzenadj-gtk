"""Settings management and system service configuration"""
import os
import json
import shutil
import logging
import threading
import subprocess

log = logging.getLogger(__name__)

CONFIG_FILE = os.path.expanduser("~/.config/ryzenadj-gtk/settings.json")
PROFILES_FILE = os.path.expanduser("~/.config/ryzenadj-gtk/profiles.json")
SYSTEM_CONFIG_DIR = "/etc/ryzenadj-gtk"
SYSTEM_CONFIG_FILE = "/etc/ryzenadj-gtk/settings.json"
SUDOERS_DROP_IN = "/etc/sudoers.d/ryzenadj-gtk"

_hardware_lock = threading.Lock()


def _run_elevated(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a shell command with root privileges"""
    executable = shutil.which(cmd[0])
    if executable:
        cmd[0] = executable
    sudo_cmd = ["sudo", "-n"] + cmd
    with _hardware_lock:
        return subprocess.run(sudo_cmd, **kwargs)


def load_settings() -> dict:
    """Load settings from settings.json"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            log.error("Failed to load settings: %s", e)
    return {}


def save_settings(settings: dict) -> None:
    """Save settings to settings.json"""
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        log.error("Failed to save settings: %s", e)


def remove_settings_from_startup(params: list[str] | str) -> tuple[bool, str]:
    """Remove one or more settings from startup configuration"""
    if isinstance(params, str):
        params = [params]
    try:
        changed = False

        user_settings = load_settings()
        for param in params:
            if param in user_settings:
                del user_settings[param]
                changed = True
        if changed:
            save_settings(user_settings)

        if os.path.exists(SYSTEM_CONFIG_FILE):
            try:
                system_settings = {}
                with open(SYSTEM_CONFIG_FILE, "r") as f:
                    system_settings = json.load(f)
                
                system_changed = False
                for param in params:
                    if param in system_settings:
                        del system_settings[param]
                        system_changed = True
                
                if system_changed:
                    with open(SYSTEM_CONFIG_FILE, "w") as f:
                        json.dump(system_settings, f, indent=2)
                    changed = True
            except Exception as e:
                log.warning("Could not update system settings for %s: %s", params, e)

        if changed:
            return True, f"Removed {', '.join(params)} from startup settings."
        else:
            return True, "Settings were not saved to startup."
    except Exception as e:
        log.error("Failed to remove settings %s from startup: %s", params, e)
        return False, str(e)


def remove_setting_from_startup(param: str) -> tuple[bool, str]:
    """Remove a single setting from startup configuration"""
    return remove_settings_from_startup([param])


def is_service_enabled() -> bool:
    """Check if systemd boot service is enabled"""
    try:
        res = subprocess.run(
            ["systemctl", "is-enabled", "ryzenadj-gtk-apply.service"],
            capture_output=True, text=True
        )
        return res.stdout.strip() == "enabled"
    except Exception:
        return False


def sync_system_settings(settings: dict) -> bool:
    """Write settings to system config file"""
    try:
        os.makedirs(SYSTEM_CONFIG_DIR, exist_ok=True)
        with open(SYSTEM_CONFIG_FILE, "w") as f:
            json.dump(settings, f, indent=2)
        return True
    except Exception as e:
        log.error("Failed to sync system settings: %s", e)
        return False


def set_service_enabled(enabled: bool) -> tuple[bool, str]:
    """Enable or disable startup systemd service"""
    if not os.path.exists("/usr/lib/systemd/system/ryzenadj-gtk-apply.service") and \
       not os.path.exists("/etc/systemd/system/ryzenadj-gtk-apply.service"):
        return False, "Startup service is not installed. Please install the application first."

    action = "enable" if enabled else "disable"
    try:
        cmd = ["systemctl", action, "--now", "ryzenadj-gtk-apply.service"]
        print(f"\n[Ryzenadj-gtk] Executing service command:\n  {' '.join(cmd)}\n", flush=True)
        res = _run_elevated(
            cmd,
            capture_output=True, text=True, timeout=10
        )
        if res.returncode != 0:
            return False, res.stderr.strip() or f"Failed to {action} service"

        if enabled:
            settings = load_settings()
            if settings:
                if not sync_system_settings(settings):
                    subprocess.run(["systemctl", "disable", "ryzenadj-gtk-apply.service"], capture_output=True)
                    return False, "Failed to write system settings to /etc/ryzenadj-gtk/settings.json. Check directory permissions."
        else:
            try:
                if os.path.exists(SYSTEM_CONFIG_FILE):
                    os.remove(SYSTEM_CONFIG_FILE)
            except Exception as e:
                log.warning("Could not delete system config file: %s", e)

        return True, f"Startup service {'enabled' if enabled else 'disabled'} successfully."
    except Exception as e:
        return False, str(e)


def factory_reset() -> tuple[bool, str]:
    """Reset all app settings and profiles to factory default"""
    try:
        if os.path.exists(CONFIG_FILE):
            os.remove(CONFIG_FILE)

        if os.path.exists(PROFILES_FILE):
            os.remove(PROFILES_FILE)

        ui_config = os.path.expanduser("~/.config/ryzenadj-gtk/ui.json")
        if os.path.exists(ui_config):
            os.remove(ui_config)

        set_service_enabled(False)
        return True, "All settings cleared and startup service disabled."
    except Exception as e:
        log.error("Factory reset failed: %s", e)
        return False, str(e)


def load_profiles() -> dict:
    """Load custom profiles from JSON"""
    if os.path.exists(PROFILES_FILE):
        try:
            with open(PROFILES_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            log.error("Failed to load profiles: %s", e)
    return {}


def save_profiles(profiles: dict) -> None:
    """Save custom profiles to JSON"""
    os.makedirs(os.path.dirname(PROFILES_FILE), exist_ok=True)
    try:
        with open(PROFILES_FILE, "w") as f:
            json.dump(profiles, f, indent=2)
    except Exception as e:
        log.error("Failed to save profiles: %s", e)
