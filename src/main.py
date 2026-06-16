"""Main GTK application coordinator"""
import os
import json
import logging
import threading

from gi.repository import Gtk, Adw, Gdk, Gio, GLib

import ryzen
import styles
import ui as ui_module
from monitor import MonitorMixin
from actions import ActionsMixin

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

APP_ID = "com.marley.ryzenadj-gtk"
APP_NAME = "Ryzenadj-gtk"
APP_VER = "1.8.4"



class RyzenadjApp(Adw.Application, MonitorMixin, ActionsMixin):
    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self.win = None
        self.css_provider = Gtk.CssProvider()
        self.theme_css_provider = Gtk.CssProvider()
        self.current_info: dict = {}
        self.pending_settings: dict = {}
        self._slider_rows: dict = {}
        self._dashboard_cards: list = []
        self.cpu_family: str = "Ryzen Processor"
        self._refresh_timer_id: int | None = None
        self._refreshing: bool = False
        self.applied_settings: dict = {}
        self.supported_params: set = set()
        self._initial_load_error: str | None = None
        self.ui_settings: dict = {
            "theme": "default",
            "auto_switch": False,
            "ac_profile": "",
            "battery_profile": "",
            "persistence_enabled": False,
            "persistence_interval": 30,
            "enthusiast_mode": False
        }
        self._persistence_ticks: int = 0
        self.last_ac_state: bool | None = None
        self.dbus_system_connection = None
        self.btn_refresh = None          # set by build_main_window
        self.btn_apply = None            # set by build_main_window
        self.window_title = None         # set by build_main_window
        self._auth_granted: bool | None = None  # Track if sudo authentication is granted (None = unchecked, True = yes, False = denied)
        self.gfx_reboot_required = False
        self._load_ui_settings()
        self.enthusiast_mode = self.ui_settings.get("enthusiast_mode", False)

    def _load_ui_settings(self):
        self.ui_config_path = os.path.expanduser("~/.config/ryzenadj-gtk/ui.json")
        if os.path.exists(self.ui_config_path):
            try:
                with open(self.ui_config_path, "r") as f:
                    self.ui_settings.update(json.load(f))
            except Exception as e:
                log.warning("Failed to load UI settings: %s", e)

    def _save_ui_settings(self):
        try:
            os.makedirs(os.path.dirname(self.ui_config_path), exist_ok=True)
            with open(self.ui_config_path, "w") as f:
                json.dump(self.ui_settings, f)
        except Exception as e:
            log.error(f"Failed to save UI settings: {e}")

    # ── Application lifecycle ──────────────────────────────────────────────────

    def do_activate(self) -> None:
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.PREFER_DARK)

        # Load standard CSS
        self.css_provider.load_from_data(styles.CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            self.css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        # Load theme dynamic CSS provider (USER priority to override platform defaults)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            self.theme_css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_USER,
        )

        # Look for theme icons in local directory too
        try:
            display = Gdk.Display.get_default()
            if display:
                theme = Gtk.IconTheme.get_for_display(display)
                curr_dir = os.path.dirname(os.path.abspath(__file__))
                theme.add_search_path(os.path.join(curr_dir, "assets"))
        except Exception as e:
            log.debug("Failed to register local icon search path: %s", e)

        # Register actions
        self._register_actions()

        # Load saved settings from disk
        saved = ryzen.load_settings()
        if saved:
            self.pending_settings.update(saved)
        self.applied_settings = dict(self.pending_settings)

        # Build and show main window
        self.win = ui_module.build_main_window(self)
        self.win.set_icon_name(APP_ID)

        GLib.set_prgname(APP_ID)
        GLib.set_application_name(APP_NAME)

        # Check if ryzenadj command is installed on system
        if not ryzen.is_ryzenadj_installed():
            missing_page = ui_module.build_dependency_missing_page(self)
            self.win.set_content(missing_page)
            self.win.present()
            return

        self.win.present()

        # Listen to D-Bus PrepareForSleep signal to handle wakes (researched how systemd triggers sleep/wake to make this work)
        try:
            self.dbus_system_connection = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            if self.dbus_system_connection:
                self.dbus_system_connection.signal_subscribe(
                    "org.freedesktop.login1",                  # sender
                    "org.freedesktop.login1.Manager",          # interface
                    "PrepareForSleep",                         # member
                    "/org/freedesktop/login1",                 # object path
                    None,                                      # arg0
                    Gio.DBusSignalFlags.NONE,
                    self.on_prepare_for_sleep                  # callback
                )
                log.info("Successfully subscribed to systemd PrepareForSleep D-Bus signal.")
        except Exception as e:
            log.warning("Failed to connect to System D-Bus for suspend/resume tracking: %s", e)

        # Read hardware info asynchronously in background
        self._do_initial_load_async()

    def _do_initial_load_async(self) -> None:
        """Fetch CPU settings in a background thread so the window shows instantly (researched using GLib.idle_add to return data safely to GTK)"""
        if self._refreshing:
            return
        self._refreshing = True

        def fetch():
            cpu_family, info, supported, auth_ok = ryzen.get_initial_data()
            GLib.idle_add(self._on_initial_load_done, cpu_family, info, supported, auth_ok)

        threading.Thread(target=fetch, daemon=True).start()

    def _sync_sliders_to_hardware_or_pending(self, info: dict, use_pending: bool = True) -> None:
        """Update slider positions to match saved or live hardware values"""
        for param, row in self._slider_rows.items():
            meta = getattr(row, "_param_meta", None)
            slider = getattr(row, "_slider", None)
            if not meta or not slider:
                continue

            is_supported = ryzen.is_parameter_supported(param, self.cpu_family, self.supported_params)

            if not is_supported:
                continue

            if use_pending and param in self.pending_settings:
                val = float(self.pending_settings[param])
            else:
                vkey = meta["value_key"]
                raw = info.get(vkey)
                if raw is not None:
                    div = meta["display_divisor"]
                    lo = meta["min"]
                    hi = meta["max"]
                    val = max(lo, min(hi, raw * div))
                else:
                    val = float(meta.get("default", meta["min"]))

            row._updating_programmatically = True
            slider.set_value(val)
            row._updating_programmatically = False

            # Update target badge labels
            if hasattr(row, "_update_val_label"):
                row._update_val_label(slider, False)

    def _on_initial_load_done(self, cpu_family: str, info: dict, supported: set, auth_ok: bool) -> bool:
        """GTK thread callback: load settings into UI or show passwordless sudo error page"""
        self._refreshing = False
        if not auth_ok:
            self._show_auth_required()
            return False
        self._auth_granted = True
        self.cpu_family = cpu_family
        self.current_info = info
        self.supported_params = supported

        # Disable sliders that this CPU model does not support
        for param, row in self._slider_rows.items():
            meta = getattr(row, "_param_meta", None)
            desc_label = getattr(row, "_desc_label", None)
            if not meta or not desc_label:
                continue
            is_supported = ryzen.is_parameter_supported(param, self.cpu_family, self.supported_params)

            row.set_sensitive(is_supported)

            desc_text = meta["desc"]
            if not is_supported:
                desc_text = f"{desc_text} <span color='#e01b24' weight='bold' size='small'>(Unsupported on this CPU)</span>"
            else:
                if param in ("min-gfxclk", "max-gfxclk"):
                    ryzenadj_native = param in (self.supported_params or set())
                    if not ryzenadj_native and ryzen.is_sysfs_gfx_clk_available():
                        desc_text = f"{desc_text} <span color='#30d158' weight='bold' size='small'>(AMDGPU Sysfs Overdrive - fallback)</span>"
            desc_label.set_markup(f"<span style='italic' size='small'>{desc_text}</span>")

        # Load default sliders values
        self._sync_sliders_to_hardware_or_pending(info, use_pending=True)
        self.applied_settings = dict(self.pending_settings)
        self._update_conflicts()

        # Hide telemetry cards if the system cannot read them
        for card in self._dashboard_cards:
            val_key = getattr(card, "_val_key", None)
            visible = val_key in info if val_key else True
            card.set_visible(visible)

        self._update_dashboard_cards()
        self._update_slider_badges()
        self._update_status_label()

        # Check for Secure Boot or Kernel Lockdown restrictions
        diag = ryzen.check_system_lockdown_status()
        if hasattr(self, "diagnostic_banner"):
            is_locked = (diag["secure_boot"] or diag["lockdown_active"]) and not diag["ryzen_smu_loaded"]
            self.diagnostic_banner.set_visible(is_locked)

            reasons = []
            if diag["secure_boot"]:
                reasons.append("Secure Boot enabled")
            if diag["lockdown_active"]:
                reasons.append(f"Lockdown active ({diag['lockdown_mode']})")
            if not diag["iomem_relaxed"]:
                reasons.append("iomem=relaxed missing")

            if reasons:
                subtitle = f"⚠️ {', '.join(reasons)}. Load 'ryzen_smu' driver or disable restrictions."
            else:
                subtitle = "⚠️ Restrictions active. Load 'ryzen_smu' driver or disable restrictions."
            self.diagnostic_banner.set_subtitle(subtitle)

        # Auto apply AC/Battery profile if setting is turned on
        if self.ui_settings.get("auto_switch", False):
            current_ac = ryzen.is_on_ac_power()
            self.last_ac_state = current_ac
            self._apply_auto_power_profile(current_ac)

        # Start background telemetry refresh loop
        if self._refresh_timer_id is None:
            self._start_refresh_timer()

        return False

    def _show_auth_required(self) -> None:
        """Show permission required screen"""
        self._auth_granted = False
        auth_page = ui_module.build_auth_required_page(self)
        self.win.set_content(auth_page)

    def _retry_auth(self) -> None:
        """Retry checking for root access"""
        self.win.set_content(self.toast_overlay)
        self._auth_granted = None
        self._do_initial_load_async()

    # ── Actions registration ───────────────────────────────────────────────────

    def _register_actions(self) -> None:
        action_reload = Gio.SimpleAction.new("reload", None)
        action_reload.connect("activate", lambda a, p: self.on_refresh_clicked(None))
        self.add_action(action_reload)

        action_about = Gio.SimpleAction.new("about", None)
        action_about.connect("activate", self.on_about_activated)
        self.add_action(action_about)

        # Manage accent color menu choices
        initial_theme = self.ui_settings.get("theme", "default")
        action_theme = Gio.SimpleAction.new_stateful(
            "theme-color",
            GLib.VariantType.new("s"),
            GLib.Variant.new_string(initial_theme)
        )
        action_theme.connect("change-state", self.on_theme_color_changed)
        self.add_action(action_theme)

        # Load default accent color
        self.on_theme_color_changed(action_theme, GLib.Variant.new_string(initial_theme))

        # Keyboard shortcut bindings
        self.set_accels_for_action("app.reload", ["F5"])

        action_apply = Gio.SimpleAction.new("apply", None)
        action_apply.connect("activate", lambda a, p: self.on_apply_clicked(None))
        self.add_action(action_apply)
        self.set_accels_for_action("app.apply", ["<Ctrl>s"])

    def on_theme_color_changed(self, action, state) -> None:
        action.set_state(state)
        color = state.get_string()

        # Save theme color choice
        self.ui_settings["theme"] = color
        self._save_ui_settings()

        theme_palettes = {
            "default": {
                "accent": "@accent_bg_color",
                "cpu_fg": "#4cc9f0", "cpu_bg": "rgba(76, 201, 240, 0.12)",      # Luminous Teal
                "gpu_fg": "#f72585", "gpu_bg": "rgba(247, 37, 133, 0.12)",     # Cyberpunk Pink
            },
            "ryzen": {
                "accent": "#ff3b30",                                           # Luminous Red
                "cpu_fg": "#ffd60a", "cpu_bg": "rgba(255, 214, 10, 0.12)",     # Neon Gold
                "gpu_fg": "#30d158", "gpu_bg": "rgba(48, 209, 88, 0.12)",      # Vibrant Green
            },
            "geforce": {
                "accent": "#76ff03",                                           # Electric Lime
                "cpu_fg": "#00e5ff", "cpu_bg": "rgba(0, 229, 255, 0.12)",      # Cyan
                "gpu_fg": "#ff4081", "gpu_bg": "rgba(255, 64, 129, 0.12)",     # Bright Pink
            },
            "intel": {
                "accent": "#0071e3",                                           # Intel Luminous Blue
                "cpu_fg": "#ffea00", "cpu_bg": "rgba(255, 234, 0, 0.12)",      # Sun Yellow
                "gpu_fg": "#00ff41", "gpu_bg": "rgba(0, 255, 65, 0.12)",       # Matrix Green
            },
            "arch": {
                "accent": "#1793d1",                                           # Arch Blue
                "cpu_fg": "#bf5af2", "cpu_bg": "rgba(191, 90, 242, 0.12)",     # Luminous Purple
                "gpu_fg": "#ff9f0a", "gpu_bg": "rgba(255, 159, 10, 0.12)",     # Orange
            },
            "saints": {
                "accent": "#af52de",                                           # Saints Purple
                "cpu_fg": "#ff3700", "cpu_bg": "rgba(255, 55, 0, 0.12)",       # Hot Orange
                "gpu_fg": "#5eebff", "gpu_bg": "rgba(94, 235, 255, 0.12)",     # Sky Blue
            },
            "noctua": {
                "accent": "#9c6644",                                           # Noctua Brown (Vibrant)
                "cpu_fg": "#e63946", "cpu_bg": "rgba(230, 57, 70, 0.12)",      # Red
                "gpu_fg": "#a8dadc", "gpu_bg": "rgba(168, 218, 220, 0.12)",     # Pale Blue
            }
        }

        palette = theme_palettes.get(color, theme_palettes["default"])
        accent = palette["accent"]

        css_lines = []
        if color != "default":
            css_lines.append(f"@define-color accent_color {accent};")
            css_lines.append(f"@define-color accent_bg_color {accent};")
            css_lines.append("@define-color accent_fg_color #ffffff;")
            css_lines.append(f"@define-color suggested_bg_color {accent};")
            css_lines.append("@define-color suggested_fg_color #ffffff;")
            css_lines.append(f"@define-color selection_bg_color {accent};")
            css_lines.append("@define-color selection_fg_color #ffffff;")

            # Override standard CSS accent classes
            css_lines.append(".suggested-action { background-color: @accent_bg_color; color: @accent_fg_color; }")
            css_lines.append("selection { background-color: @accent_bg_color; color: @accent_fg_color; }")

        # Set dynamic color definitions
        css_lines.append(f"@define-color cpu_badge_fg {palette['cpu_fg']};")
        css_lines.append(f"@define-color cpu_badge_bg {palette['cpu_bg']};")
        css_lines.append(f"@define-color gpu_badge_fg {palette['gpu_fg']};")
        css_lines.append(f"@define-color gpu_badge_bg {palette['gpu_bg']};")

        css = "\n".join(css_lines)
        self.theme_css_provider.load_from_data(css)

    # ── Toast ──────────────────────────────────────────────────────────────────

    def _show_toast(self, msg: str, is_error: bool = False) -> None:
        if hasattr(self, "_current_toast") and self._current_toast:
            try:
                self._current_toast.dismiss()
            except Exception:
                pass
        prefix = "⚠ " if is_error else ""
        toast = Adw.Toast.new(f"{prefix}{msg}")
        toast.set_timeout(2)
        self._current_toast = toast
        if hasattr(self, "toast_overlay") and self.toast_overlay:
            self.toast_overlay.add_toast(toast)
        elif isinstance(self.win, Adw.ApplicationWindow):
            try:
                self.win.add_toast(toast)
            except AttributeError:
                log.warning("Adw.ApplicationWindow lacks add_toast, toast discarded: %s", msg)

    def _set_actions_sensitive(self, sensitive: bool) -> None:
        """Disable buttons while we are writing settings to hardware"""
        if hasattr(self, "btn_apply") and self.btn_apply:
            self.btn_apply.set_sensitive(sensitive)
        if hasattr(self, "btn_ps") and self.btn_ps:
            self.btn_ps.set_sensitive(sensitive)
        if hasattr(self, "btn_mp") and self.btn_mp:
            self.btn_mp.set_sensitive(sensitive)
        if hasattr(self, "btn_refresh") and self.btn_refresh:
            self.btn_refresh.set_sensitive(sensitive)

    # ── About ──────────────────────────────────────────────────────────────────

    def on_about_activated(self, _action, _param) -> None:
        about = Adw.AboutDialog()
        about.set_application_name(APP_NAME)
        about.set_application_icon(APP_ID)
        about.set_version(APP_VER)
        about.set_developer_name("marley")
        about.set_website("https://github.com/marleylinux/Ryzenadj-gtk")
        about.set_issue_url("https://github.com/marleylinux/Ryzenadj-gtk/issues")
        about.set_license_type(Gtk.License.GPL_3_0)
        about.set_comments(
            "A modern GTK4 / Libadwaita graphical wrapper for ryzenadj.\n"
            "Adjust AMD Ryzen power management settings with ease."
        )
        about.set_developers(["marley"])
        about.present(self.win)
