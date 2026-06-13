"""Page layouts, dashboard, and profiles manager views"""
import os
import subprocess
import logging
import ryzen

from gi.repository import Gtk, Adw, Gdk
try:
    from main import APP_VER
except ImportError:
    APP_VER = "1.8.1"

from widgets import (
    get_cpu_name,
    _fmt,
    _build_slider_row,
    _make_card_grid,
    _build_section_header
)

log = logging.getLogger(__name__)


def build_dependency_missing_page(app) -> Adw.ToolbarView:
    """Show error page when ryzenadj is not installed"""
    toolbar = Adw.ToolbarView()

    header = Adw.HeaderBar()
    header.add_css_class("main-header")
    win_title = Adw.WindowTitle()
    win_title.set_title("Ryzenadj-gtk")
    win_title.set_subtitle("Dependency Missing")
    header.set_title_widget(win_title)
    toolbar.add_top_bar(header)

    status = Adw.StatusPage()
    status.set_icon_name("software-update-urgent-symbolic")
    status.set_title("ryzenadj Not Found")
    status.set_description(
        "The core dependency 'ryzenadj' is missing from your system.\n\n"
        "Ryzenadj-gtk is a graphical wrapper and requires the command-line tool to function.\n\n"
        "Please install it from the AUR:\n"
        "  • yay -S ryzenadj (Recommended)\n"
        "  • yay -S ryzenadj-git (Alternative)\n\n"
        "After installing, please restart this application."
    )

    toolbar.set_content(status)
    return toolbar


def build_auth_required_page(app) -> Adw.ToolbarView:
    """Show authorization screen if passwordless sudo rules are missing.
    The embedded script must stay in sync with the rules produced by install.sh and PKGBUILD.
    """
    toolbar = Adw.ToolbarView()

    header = Adw.HeaderBar()
    header.add_css_class("main-header")
    win_title = Adw.WindowTitle()
    win_title.set_title("Ryzenadj-gtk")
    win_title.set_subtitle("System Configuration Required")
    header.set_title_widget(win_title)
    toolbar.add_top_bar(header)

    status = Adw.StatusPage()
    status.set_icon_name("dialog-password-symbolic")
    status.set_title("Background Access Required")
    status.set_description(
        "The installer should have already set up passwordless sudo for ryzenadj.\n\n"
        "Ryzenadj-gtk needs this background rule to monitor and adjust hardware "
        "without constantly asking for your password."
    )

    btn_fix = Gtk.Button(label="Grant Background Access")
    btn_fix.add_css_class("suggested-action")
    btn_fix.add_css_class("pill")
    btn_fix.set_halign(Gtk.Align.CENTER)

    def on_fix(_b):
        current_user = os.environ.get("USER") or os.environ.get("LOGNAME") or ""
        if not current_user:
            try:
                import pwd
                current_user = pwd.getpwuid(os.getuid()).pw_name
            except Exception:
                current_user = ""
        if not current_user:
            if app and hasattr(app, "_show_toast"):
                app._show_toast("Could not determine current username.", is_error=True)
            return

        script = f"""set -e
TMP=$(mktemp /tmp/ryzenadj-sudoers.XXXXXX)
cat > "$TMP" << 'INNEREOF'
{current_user} ALL=(ALL) NOPASSWD: /usr/bin/ryzenadj
{current_user} ALL=(ALL) NOPASSWD: /usr/local/bin/ryzenadj
{current_user} ALL=(ALL) NOPASSWD: /usr/bin/systemctl enable ryzenadj-gtk-apply.service
{current_user} ALL=(ALL) NOPASSWD: /usr/bin/systemctl disable ryzenadj-gtk-apply.service
{current_user} ALL=(ALL) NOPASSWD: /usr/bin/systemctl enable --now ryzenadj-gtk-apply.service
{current_user} ALL=(ALL) NOPASSWD: /usr/bin/systemctl disable --now ryzenadj-gtk-apply.service
{current_user} ALL=(ALL) NOPASSWD: /usr/bin/systemctl is-enabled ryzenadj-gtk-apply.service
{current_user} ALL=(ALL) NOPASSWD: /usr/bin/tee /sys/class/drm/card*/device/pp_od_clk_voltage
{current_user} ALL=(ALL) NOPASSWD: /usr/bin/tee /sys/class/drm/card*/device/power_dpm_force_performance_level
INNEREOF
if visudo -cf "$TMP" > /dev/null 2>&1; then
    mv "$TMP" /etc/sudoers.d/ryzenadj-gtk
    chmod 440 /etc/sudoers.d/ryzenadj-gtk
    chown root:root /etc/sudoers.d/ryzenadj-gtk
else
    rm -f "$TMP"
    exit 1
fi
"""
        try:
            res = subprocess.run(["pkexec", "sh", "-c", script])
            if res.returncode == 0:
                app._retry_auth()
            else:
                if app and hasattr(app, "_show_toast"):
                    app._show_toast(f"Authorization failed (Code {res.returncode})", is_error=True)
        except Exception as e:
            if app and hasattr(app, "_show_toast"):
                app._show_toast(f"Error launching pkexec: {e}", is_error=True)

    btn_fix.connect("clicked", on_fix)

    btn_reboot = Gtk.Button(label="Reboot Now")
    btn_reboot.add_css_class("destructive-action")
    btn_reboot.add_css_class("pill")
    btn_reboot.set_halign(Gtk.Align.CENTER)
    btn_reboot.set_margin_top(8)

    def on_reboot(_b):
        subprocess.run(["pkexec", "systemctl", "reboot"], check=False)

    btn_reboot.connect("clicked", on_reboot)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    box.append(btn_fix)
    box.append(btn_reboot)
    status.set_child(box)

    toolbar.set_content(status)
    return toolbar


def _build_dashboard_page(app) -> Gtk.ScrolledWindow:
    """Build system telemetry dashboard with live graph bars"""
    app._dashboard_cards = []

    scrolled = Gtk.ScrolledWindow()
    scrolled.set_vexpand(True)
    scrolled.set_name("dashboard")
    scrolled.get_title = lambda: "Dashboard"

    clamp = Adw.Clamp()
    clamp.set_maximum_size(1000)
    clamp.set_margin_top(24)
    clamp.set_margin_bottom(32)
    clamp.set_margin_start(16)
    clamp.set_margin_end(16)
    scrolled.set_child(clamp)

    main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    clamp.set_child(main_box)

    hero_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
    hero_box.add_css_class("hero-box")
    hero_box.set_halign(Gtk.Align.FILL)

    status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    status_box.set_valign(Gtk.Align.CENTER)
    status_pill = Gtk.Label(label="● Live")
    status_pill.add_css_class("live-status-pill")
    status_box.append(status_pill)
    hero_box.append(status_box)

    center_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
    center_content.set_hexpand(True)
    center_content.set_halign(Gtk.Align.CENTER)

    hero_icon = Gtk.Image.new_from_icon_name("system-run-symbolic")
    hero_icon.set_pixel_size(48)
    hero_icon.add_css_class("hero-icon")
    center_content.append(hero_icon)

    text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    text_box.set_valign(Gtk.Align.CENTER)

    title_lbl = Gtk.Label(label="Ryzen Dashboard")
    title_lbl.add_css_class("hero-title")
    title_lbl.set_halign(Gtk.Align.START)
    text_box.append(title_lbl)

    subtitle_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)

    subtitle_lbl = Gtk.Label(label="Active monitoring for")
    subtitle_lbl.add_css_class("hero-subtitle")
    subtitle_box.append(subtitle_lbl)

    cpu_badge = Gtk.Label(label=get_cpu_name())
    cpu_badge.add_css_class("hero-cpu-badge")
    subtitle_box.append(cpu_badge)

    text_box.append(subtitle_box)
    center_content.append(text_box)
    hero_box.append(center_content)

    right_spacer = Gtk.Box()
    right_spacer.set_size_request(80, -1)
    hero_box.append(right_spacer)
    main_box.append(hero_box)

    diagnostic_card = Adw.ActionRow()
    diagnostic_card.set_title("System Memory Lockdown Detected")
    diagnostic_card.set_subtitle("Secure Boot or Kernel Lockdown is active, which blocks ryzenadj from writing parameters to SMU.")
    diagnostic_card.add_css_class("diagnostic-warning-row")
    diagnostic_card.set_visible(False)

    app.diagnostic_banner = diagnostic_card

    grp_diag = Adw.PreferencesGroup()
    grp_diag.add(diagnostic_card)
    grp_diag.set_margin_top(16)
    main_box.append(grp_diag)

    main_box.append(_build_section_header("Power Envelope", "battery-symbolic"))

    grp_power = Adw.PreferencesGroup()
    grp_power.add_css_class("dashboard-group")

    power_grid = _make_card_grid(app, [
        ("STAPM VALUE",   "STAPM LIMIT",    "STAPM",     "W", "battery-symbolic"),
        ("PPT VALUE FAST","PPT LIMIT FAST", "PPT Fast",  "W", "battery-symbolic"),
        ("PPT VALUE SLOW","PPT LIMIT SLOW", "PPT Slow",  "W", "battery-symbolic"),
        ("PPT VALUE APU", "PPT LIMIT APU",  "APU PPT",   "W", "battery-symbolic"),
    ])
    grp_power.add(power_grid)
    main_box.append(grp_power)

    main_box.append(_build_section_header("Electrical Current", "thunderbolt-symbolic"))

    grp_current = Adw.PreferencesGroup()
    grp_current.add_css_class("dashboard-group")

    current_grid = _make_card_grid(app, [
        ("TDC VALUE VDD", "TDC LIMIT VDD", "TDC VDD", "A", "thunderbolt-symbolic"),
        ("TDC VALUE SOC", "TDC LIMIT SOC", "TDC SoC", "A", "thunderbolt-symbolic"),
        ("EDC VALUE VDD", "EDC LIMIT VDD", "EDC VDD", "A", "thunderbolt-symbolic"),
        ("EDC VALUE SOC", "EDC LIMIT SOC", "EDC SoC", "A", "thunderbolt-symbolic"),
    ])
    grp_current.add(current_grid)
    main_box.append(grp_current)

    main_box.append(_build_section_header("Thermal Status", "sensors-temperature-symbolic"))

    grp_thermal = Adw.PreferencesGroup()
    grp_thermal.add_css_class("dashboard-group")

    thermal_flow = _make_card_grid(app, [
        ("THM VALUE CORE", "THM LIMIT CORE", "CPU Die",       "°C", "sensors-temperature-symbolic"),
        ("STT VALUE APU",  "STT LIMIT APU",  "APU Skin",      "°C", "sensors-temperature-symbolic"),
        ("STT VALUE dGPU", "STT LIMIT dGPU", "dGPU Skin",     "°C", "sensors-temperature-symbolic"),
    ])
    grp_thermal.add(thermal_flow)
    main_box.append(grp_thermal)

    return scrolled


def _build_settings_page(app) -> Gtk.ScrolledWindow:
    """Build settings page containing automation, persistence, startup and tuning, and about sections"""
    scrolled = Gtk.ScrolledWindow()
    scrolled.set_vexpand(True)
    scrolled.set_name("settings")
    scrolled.get_title = lambda: "Settings"

    clamp = Adw.Clamp()
    clamp.set_maximum_size(1000)
    clamp.set_margin_top(24)
    clamp.set_margin_bottom(32)
    clamp.set_margin_start(16)
    clamp.set_margin_end(16)
    scrolled.set_child(clamp)

    main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    clamp.set_child(main_box)

    # Power Automation
    main_box.append(_build_section_header("Power Automation", "battery-symbolic"))

    grp_automation = Adw.PreferencesGroup()
    grp_automation.set_description("Automatically swap profiles based on power supply charging state")

    switch_auto = Adw.SwitchRow()
    switch_auto.set_title("Auto-switch profiles on power change")
    switch_auto.set_subtitle("Automatically switch profiles when AC charger is plugged in or disconnected")
    switch_auto.set_icon_name("media-playlist-shuffle-symbolic")
    switch_auto.set_active(app.ui_settings.get("auto_switch", False))
    grp_automation.add(switch_auto)

    ac_row = Adw.ComboRow()
    ac_row.set_title("Plugged into AC Power")
    ac_row.set_subtitle("Profile applied when connected to charger")
    ac_row.set_icon_name("battery-full-charging-symbolic")
    grp_automation.add(ac_row)

    bat_row = Adw.ComboRow()
    bat_row.set_title("Running on Battery")
    bat_row.set_subtitle("Profile applied when running on battery")
    bat_row.set_icon_name("battery-symbolic")
    grp_automation.add(bat_row)

    main_box.append(grp_automation)

    def update_automation_dropdowns():
        profiles = list(sorted(ryzen.load_profiles().keys()))
        options = ["Stock (No Profile)", "⚡ Power Saving Preset", "🚀 Max Performance Preset"] + profiles
        option_keys = ["", "__power_saving__", "__max_performance__"] + profiles
        
        model_ac = Gtk.StringList.new(options)
        model_bat = Gtk.StringList.new(options)
        
        ac_row.set_model(model_ac)
        bat_row.set_model(model_bat)
        
        saved_ac = app.ui_settings.get("ac_profile", "")
        saved_bat = app.ui_settings.get("battery_profile", "")
        
        try:
            ac_idx = option_keys.index(saved_ac)
            ac_row.set_selected(ac_idx)
        except ValueError:
            ac_row.set_selected(0)
            
        try:
            bat_idx = option_keys.index(saved_bat)
            bat_row.set_selected(bat_idx)
        except ValueError:
            if not saved_bat and "__power_saving__" in option_keys:
                bat_row.set_selected(1)
            else:
                bat_row.set_selected(0)

        ac_row._option_keys = option_keys
        bat_row._option_keys = option_keys

    app.update_automation_dropdowns = update_automation_dropdowns
    update_automation_dropdowns()

    def on_auto_switch_toggled(switch_row, _spec):
        active = switch_row.get_active()
        app.ui_settings["auto_switch"] = active
        app._save_ui_settings()
        ac_row.set_sensitive(active)
        bat_row.set_sensitive(active)
        if active:
            current_ac = ryzen.is_on_ac_power()
            app.last_ac_state = current_ac
            app._apply_auto_power_profile(current_ac)

    def on_ac_selected(row, _spec):
        idx = row.get_selected()
        if hasattr(row, "_option_keys") and idx < len(row._option_keys):
            app.ui_settings["ac_profile"] = row._option_keys[idx]
            app._save_ui_settings()
            if app.ui_settings.get("auto_switch", False) and ryzen.is_on_ac_power():
                app._apply_auto_power_profile(True)

    def on_bat_selected(row, _spec):
        idx = row.get_selected()
        if hasattr(row, "_option_keys") and idx < len(row._option_keys):
            app.ui_settings["battery_profile"] = row._option_keys[idx]
            app._save_ui_settings()
            if app.ui_settings.get("auto_switch", False) and not ryzen.is_on_ac_power():
                app._apply_auto_power_profile(False)

    switch_auto.connect("notify::active", on_auto_switch_toggled)
    ac_row.connect("notify::selected", on_ac_selected)
    bat_row.connect("notify::selected", on_bat_selected)

    ac_row.set_sensitive(app.ui_settings.get("auto_switch", False))
    bat_row.set_sensitive(app.ui_settings.get("auto_switch", False))

    # Persistence Guard
    main_box.append(_build_section_header("Persistence Guard", "system-lock-screen-symbolic"))

    grp_persistence = Adw.PreferencesGroup()
    grp_persistence.set_description("Periodically verify and re-apply settings to counter thermal or system power overrides")

    switch_persist = Adw.SwitchRow()
    switch_persist.set_title("Enable Persistence Guard")
    switch_persist.set_subtitle("⚠️ Re-applies active registers periodically. Lower verification intervals may cause system overhead or responsiveness impact depending on your configuration.")
    switch_persist.set_icon_name("security-high-symbolic")
    switch_persist.set_active(app.ui_settings.get("persistence_enabled", False))
    grp_persistence.add(switch_persist)

    persist_interval_row = Adw.ComboRow()
    persist_interval_row.set_title("Verification Interval")
    persist_interval_row.set_subtitle("Time elapsed between checks and re-applications")
    persist_interval_row.set_icon_name("alarm-symbolic")
    
    interval_options = [
        "5 seconds (High Overhead)",
        "10 seconds (Medium Overhead)",
        "30 seconds (Recommended)",
        "60 seconds (Lightweight)"
    ]
    interval_values = [5, 10, 30, 60]
    
    model_persist = Gtk.StringList.new(interval_options)
    persist_interval_row.set_model(model_persist)
    
    saved_interval = app.ui_settings.get("persistence_interval", 30)
    try:
        selected_idx = interval_values.index(saved_interval)
        persist_interval_row.set_selected(selected_idx)
    except ValueError:
        persist_interval_row.set_selected(2)

    grp_persistence.add(persist_interval_row)
    main_box.append(grp_persistence)

    def on_persistence_toggled(switch_row, _spec):
        active = switch_row.get_active()
        app.ui_settings["persistence_enabled"] = active
        app._persistence_ticks = 0
        app._save_ui_settings()
        persist_interval_row.set_sensitive(active)

    def on_persistence_interval_selected(row, _spec):
        idx = row.get_selected()
        if idx < len(interval_values):
            app.ui_settings["persistence_interval"] = interval_values[idx]
            app._persistence_ticks = 0
            app._save_ui_settings()

    switch_persist.connect("notify::active", on_persistence_toggled)
    persist_interval_row.connect("notify::selected", on_persistence_interval_selected)
    
    persist_interval_row.set_sensitive(app.ui_settings.get("persistence_enabled", False))

    # System and Tuning
    main_box.append(_build_section_header("System and Tuning", "preferences-system-symbolic"))

    grp_service = Adw.PreferencesGroup()
    grp_service.set_description("Manage boot persistence and extreme tuning bounds")

    switch_row = Adw.SwitchRow()
    switch_row.set_title("Apply settings on startup")
    switch_row.set_subtitle("Automatically write saved limits to Ryzen hardware on system boot via systemd service")
    switch_row.set_icon_name("system-run-symbolic")
    switch_row.set_active(ryzen.is_service_enabled())
    
    app.switch_startup = switch_row
    switch_row.connect("notify::active", app.on_startup_switch_toggled)
    grp_service.add(switch_row)

    switch_enthusiast = Adw.SwitchRow()
    switch_enthusiast.set_title("Enthusiast Mode (Extreme Tuning)")
    switch_enthusiast.set_subtitle("Extend power limits up to 250W (250,000 mW) and currents up to 500A (Ensure high-wattage PSU and adequate cooling!)")
    switch_enthusiast.set_icon_name("dialog-warning-symbolic")
    switch_enthusiast.set_active(app.enthusiast_mode)
    
    app.switch_enthusiast = switch_enthusiast
    switch_enthusiast.connect("notify::active", app.on_enthusiast_toggled)
    grp_service.add(switch_enthusiast)
    main_box.append(grp_service)

    # About Section
    main_box.append(_build_section_header("About", "help-about-symbolic"))
    
    group_about = Adw.PreferencesGroup()
    group_about.set_title("Application Details")
    
    row_version = Adw.ActionRow()
    row_version.set_title("Version")
    row_version.set_subtitle(APP_VER)
    group_about.add(row_version)
    
    row_author = Adw.ActionRow()
    row_author.set_title("Developer")
    row_author.set_subtitle("Marley (marleylinux)")
    group_about.add(row_author)
    
    row_repo = Adw.ActionRow()
    row_repo.set_title("Repository")
    row_repo.set_subtitle("https://github.com/marleylinux/Ryzenadj-gtk")
    
    btn_link = Gtk.Button(icon_name="document-open-symbolic")
    btn_link.set_tooltip_text("Open GitHub Repo")
    btn_link.set_valign(Gtk.Align.CENTER)
    btn_link.connect("clicked", lambda b: Gtk.show_uri(app.win, "https://github.com/marleylinux/Ryzenadj-gtk", Gdk.CURRENT_TIME))
    row_repo.add_suffix(btn_link)
    group_about.add(row_repo)
    main_box.append(group_about)

    # Factory Reset
    btn_reset = Gtk.Button()
    btn_reset.set_tooltip_text("Wipe all settings, disable startup service, and prepare for reboot")
    btn_reset.add_css_class("destructive-action")
    btn_reset.add_css_class("pill")
    btn_reset.set_margin_top(24)
    btn_reset.set_margin_bottom(16)
    btn_reset.set_halign(Gtk.Align.CENTER)
    
    btn_reset_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    btn_reset_icon = Gtk.Image.new_from_icon_name("edit-clear-all-symbolic")
    btn_reset_label = Gtk.Label(label="Factory Reset")
    btn_reset_content.append(btn_reset_icon)
    btn_reset_content.append(btn_reset_label)
    btn_reset.set_child(btn_reset_content)
    
    btn_reset.connect("clicked", app.on_factory_reset_clicked)
    main_box.append(btn_reset)

    return scrolled


def _build_slider_page(app, title: str, icon: str, name: str, groups: list) -> Gtk.ScrolledWindow:
    """Build slider configuration pages dynamically based on category lists"""
    scrolled = Gtk.ScrolledWindow()
    scrolled.set_vexpand(True)
    scrolled.set_name(name)
    scrolled.get_title = lambda: title
    
    clamp = Adw.Clamp()
    clamp.set_maximum_size(1000)
    clamp.set_margin_top(24)
    clamp.set_margin_bottom(32)
    clamp.set_margin_start(16)
    clamp.set_margin_end(16)
    scrolled.set_child(clamp)
    
    main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    clamp.set_child(main_box)

    for grp_title, grp_desc, param_list in groups:
        header_box = _build_section_header(grp_title, icon)
        main_box.append(header_box)
        
        grp = Adw.PreferencesGroup()
        if grp_desc:
            grp.set_description(grp_desc)

        for meta in param_list:
            param = meta["param"]
            is_supported = ryzen.is_parameter_supported(
                param,
                getattr(app, "cpu_family", "Unknown"),
                getattr(app, "supported_params", set()),
            )

            row = _build_slider_row(meta, app.current_info, app.pending_settings, app, is_supported)
            grp.add(row)
            app._slider_rows[meta["param"]] = row

        main_box.append(grp)

    return scrolled


def _build_profiles_page(app) -> Gtk.ScrolledWindow:
    """Build the profiles manager page so we can save and load settings"""
    scrolled = Gtk.ScrolledWindow()
    scrolled.set_vexpand(True)
    scrolled.set_name("profiles")
    scrolled.get_title = lambda: "Profiles"
    
    clamp = Adw.Clamp()
    clamp.set_maximum_size(1000)
    clamp.set_margin_top(24)
    clamp.set_margin_bottom(32)
    clamp.set_margin_start(16)
    clamp.set_margin_end(16)
    scrolled.set_child(clamp)
    
    main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    clamp.set_child(main_box)

    main_box.append(_build_section_header("Save Current Profile", "document-save-symbolic"))
    
    grp_save = Adw.PreferencesGroup()
    grp_save.set_description("Save your current tuning state as a reusable power profile")

    name_row = Adw.EntryRow()
    name_row.set_title("Profile Name")
    
    btn_save = Gtk.Button(label="Save Profile")
    btn_save.add_css_class("suggested-action")
    btn_save.add_css_class("pill")
    btn_save.set_valign(Gtk.Align.CENTER)
    
    name_row.add_suffix(btn_save)
    grp_save.add(name_row)
    main_box.append(grp_save)

    main_box.append(_build_section_header("Managed Profiles", "bookmarks-symbolic"))

    grp_list = Adw.PreferencesGroup()
    grp_list.set_description("Manage and apply your custom Ryzen power profiles")
    main_box.append(grp_list)

    list_box = Gtk.ListBox()
    list_box.add_css_class("boxed-list")
    grp_list.add(list_box)

    app.profiles_listbox = list_box
    app.profile_name_row = name_row

    def refresh_profiles():
        # Clear out existing rows first (i kinda looked up how to clear GTK list_box children cleanly)
        while True:
            child = list_box.get_first_child()
            if not child:
                break
            list_box.remove(child)

        # Keep UI dropdowns in sync so they show the updated profiles list
        if hasattr(app, "update_automation_dropdowns") and app.update_automation_dropdowns:
            app.update_automation_dropdowns()

        profiles = ryzen.load_profiles()
        # Show a placeholder row if no profiles are configured yet
        if not profiles:
            empty_row = Adw.ActionRow()
            empty_row.set_title("No saved profiles")
            empty_row.set_subtitle("Type a name above to create your first custom profile.")
            empty_row.set_sensitive(False)
            list_box.append(empty_row)
            return

        for name, settings in sorted(profiles.items()):
            row = Adw.ActionRow()
            row.set_title(name)
            
            # Format and show a quick preview of the saved parameter values
            summary_parts = []
            for k, v in settings.items():
                meta = next((m for m in ryzen.SETTINGS_PARAMS if m["param"] == k), None)
                if meta:
                    val_str = _fmt(v, meta["display_divisor"], meta["display_unit"])
                    summary_parts.append(f"{meta['label']}: {val_str}")

            # Truncate subtitle preview if there are too many parameters so it doesn't get cluttered
            max_summary = 5
            if len(summary_parts) > max_summary:
                overflow = len(summary_parts) - max_summary
                summary_parts = summary_parts[:max_summary]
                summary_parts.append(f"... and {overflow} more")
            summary_text = ", ".join(summary_parts) if summary_parts else "No parameters configured"
            row.set_subtitle(summary_text)

            btn_apply = Gtk.Button(icon_name="object-select-symbolic")
            btn_apply.add_css_class("flat")
            btn_apply.set_tooltip_text(f"Apply '{name}' profile")
            
            btn_delete = Gtk.Button(icon_name="user-trash-symbolic")
            btn_delete.add_css_class("flat")
            btn_delete.add_css_class("destructive-action")
            btn_delete.set_tooltip_text(f"Delete '{name}' profile")

            # Helper functions to build callbacks (closures needed here so they remember their target profile name/settings)
            def make_on_apply(p_name, p_settings):
                def on_apply(_btn):
                    # 1. Clear out any pending or applied settings that are not in the profile
                    keys_to_remove = [k for k in app.pending_settings if k not in p_settings]
                    for k in keys_to_remove:
                        del app.pending_settings[k]
                    
                    keys_to_remove_applied = [k for k in app.applied_settings if k not in p_settings]
                    for k in keys_to_remove_applied:
                        del app.applied_settings[k]

                    # 2. Update/apply profile settings
                    for param, val in p_settings.items():
                        app.pending_settings[param] = val

                    # 3. Update all sliders in the UI
                    for param, row_widget in app._slider_rows.items():
                        slider = getattr(row_widget, "_slider", None)
                        if not slider:
                            continue
                        
                        meta = getattr(row_widget, "_param_meta", None)
                        if not meta:
                            continue
                            
                        row_widget._updating_programmatically = True
                        if param in p_settings:
                            val = float(p_settings[param])
                            slider.set_value(val)
                        else:
                            # Reset to hardware value or default
                            vkey = meta["value_key"]
                            cur_raw = app.current_info.get(vkey)
                            if cur_raw is not None:
                                val = cur_raw * meta["display_divisor"]
                            else:
                                val = float(meta.get("default", meta["min"]))
                            slider.set_value(val)
                        row_widget._updating_programmatically = False
                        
                        if hasattr(row_widget, "_update_val_label"):
                            row_widget._update_val_label(slider, param in p_settings)

                    app._show_toast(f"Applying profile '{p_name}'...", is_error=False)
                    
                    # 4. Determine diff and execute apply
                    diff_settings = {
                        k: v for k, v in p_settings.items()
                        if app.applied_settings.get(k) != v
                    }
                    if diff_settings:
                        app._execute_apply(diff_settings)
                    else:
                        app._show_toast(f"Profile '{p_name}' is already applied.", is_error=False)
                return on_apply

            def make_on_delete(p_name):
                def on_delete(_btn):
                    all_profiles = ryzen.load_profiles()
                    if p_name in all_profiles:
                        del all_profiles[p_name]
                        ryzen.save_profiles(all_profiles)
                        app._show_toast(f"Profile '{p_name}' deleted.", is_error=False)
                        refresh_profiles()
                return on_delete

            btn_apply.connect("clicked", make_on_apply(name, settings))
            btn_delete.connect("clicked", make_on_delete(name))

            suffix_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            suffix_box.append(btn_apply)
            suffix_box.append(btn_delete)
            row.add_suffix(suffix_box)
            list_box.append(row)

    def on_save_clicked(_btn):
        name = name_row.get_text().strip()
        if not name:
            app._show_toast("Please enter a profile name.", is_error=True)
            return
        
        current_settings = dict(app.pending_settings)
        if not current_settings:
            app._show_toast("No settings are configured to save.", is_error=True)
            return
            
        profiles = ryzen.load_profiles()
        profiles[name] = current_settings
        ryzen.save_profiles(profiles)
        
        name_row.set_text("")
        app._show_toast(f"Profile '{name}' saved successfully!", is_error=False)
        refresh_profiles()

    btn_save.connect("clicked", on_save_clicked)
    app.refresh_profiles_list = refresh_profiles
    refresh_profiles()

    return scrolled
