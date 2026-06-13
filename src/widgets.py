"""UI elements, sliders, formatting helpers, and card structures"""
import logging
import platform
import subprocess
import ryzen

from gi.repository import Gtk, Adw

log = logging.getLogger(__name__)

# Cache to store CPU name so we don't read cpuinfo repeatedly
_cpu_name_cache: str | None = None


def get_cpu_name() -> str:
    """Get CPU name from cpuinfo and format it nicely"""
    global _cpu_name_cache
    if _cpu_name_cache is not None:
        return _cpu_name_cache
    try:
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if "model name" in line:
                    name = line.split(":", 1)[1].strip()
                    if " w/" in name:
                        name = name.split(" w/", 1)[0]
                    if " with " in name:
                        name = name.split(" with ", 1)[0]
                    name = name.replace("Processor", "")
                    if len(name) > 35:
                        name = name[:32] + "..."
                    _cpu_name_cache = name.strip()
                    return _cpu_name_cache
    except Exception:
        pass
    _cpu_name_cache = platform.processor() or "AMD Ryzen"
    return _cpu_name_cache


def _bar_class(fraction: float) -> str:
    """Determine color classification for monitor card progress bars"""
    if fraction < 0.5:
        return "low"
    elif fraction < 0.8:
        return "medium"
    return "high"


def _fmt(value: float, divisor: float, unit: str) -> str:
    """Format numbers for display with their correct units"""
    v = value / divisor
    if unit == "":
        return f"{v:+.0f}" if v != 0 else "0"
    if unit in ("mW", "mA"):
        return f"{v:.0f} {unit}"
    if unit in ("W", "A"):
        return f"{v:.1f} {unit}"
    if unit == "°C":
        return f"{v:.1f}{unit}"
    if unit == "s":
        return f"{v:.0f} {unit}"
    return f"{v:.1f} {unit}"


def _fmt_limit(limit: float | None, unit: str) -> str:
    """Format limit values for display (none or 0 means Auto)"""
    if limit is None or limit < 0:
        return "Auto"
    if limit == 0:
        return "Auto"
    if unit == "°C":
        return f"Limit: {limit:.0f}°C"
    if unit == "s":
        return f"Limit: {limit:.0f}s"
    return f"Limit: {limit:.1f} {unit}"


def _build_slider_row(meta: dict, current_info: dict, pending: dict, app=None, is_supported: bool = True) -> Gtk.ListBoxRow:
    """Build a slider row with +/- buttons and live telemetry labels"""
    param = meta["param"]
    desc  = meta["desc"]
    lo    = meta["min"]
    hi    = meta["max"]

    is_sysfs_fallback = False
    if param in ("min-gfxclk", "max-gfxclk"):
        if app and hasattr(app, "supported_params"):
            ryzenadj_native = param in (app.supported_params or set())
            if not ryzenadj_native and ryzen.is_sysfs_gfx_clk_available():
                is_sysfs_fallback = True
                sysfs_range = ryzen.get_sysfs_gfx_clk_hardware_range()
                lo = sysfs_range[0]
                hi = sysfs_range[1]

    div   = meta["display_divisor"]
    dunit = meta["display_unit"]
    vkey  = meta["value_key"]

    row = Gtk.ListBoxRow()
    row.add_css_class("slider-row-item")
    row.set_selectable(False)
    row.set_activatable(False)

    main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    main_box.set_margin_start(16)
    main_box.set_margin_end(16)
    main_box.set_margin_top(12)
    main_box.set_margin_bottom(12)

    top_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    
    text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    text_box.set_hexpand(True)
    
    flag_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    
    title_label = Gtk.Label(xalign=0)
    title_label.set_markup(f"<span font_family='monospace' weight='bold' size='medium'>--{param}</span>")
    title_label.add_css_class("slider-row-flag")
    flag_box.append(title_label)

    if meta.get("is_gpu", False):
        gpu_tag_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        gpu_tag_box.add_css_class("gpu-badge")
        gpu_tag_box.set_valign(Gtk.Align.CENTER)
        
        gpu_icon = Gtk.Image.new_from_icon_name("video-display-symbolic")
        gpu_icon.set_pixel_size(12)
        gpu_tag_box.append(gpu_icon)
        
        gpu_label = Gtk.Label(label="GPU")
        gpu_tag_box.append(gpu_label)
        
        flag_box.append(gpu_tag_box)
    elif meta.get("is_cpu", False):
        cpu_tag_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        cpu_tag_box.add_css_class("cpu-badge")
        cpu_tag_box.set_valign(Gtk.Align.CENTER)
        
        cpu_icon = Gtk.Image.new_from_icon_name("system-run-symbolic")
        cpu_icon.set_pixel_size(12)
        cpu_tag_box.append(cpu_icon)
        
        cpu_label = Gtk.Label(label="CPU")
        cpu_tag_box.append(cpu_label)
        
        flag_box.append(cpu_tag_box)
        
    text_box.append(flag_box)

    desc_text = desc
    if not is_supported:
        desc_text = f"{desc} <span color='#e01b24' weight='bold' size='small'>(Unsupported on this CPU)</span>"
    elif is_sysfs_fallback:
        desc_text = f"{desc} <span color='#30d158' weight='bold' size='small'>(AMDGPU Sysfs Overdrive - fallback)</span>"

    desc_label = Gtk.Label(xalign=0)
    desc_label.set_markup(f"<span style='italic' size='small'>{desc_text}</span>")
    desc_label.add_css_class("slider-row-desc")
    
    text_box.append(desc_label)
    top_box.append(text_box)

    cur_raw = current_info.get(vkey)
    if cur_raw is not None:
        cur_text = f"Live: {_fmt(cur_raw, 1, dunit)}"
        cur_cli = cur_raw * div
    else:
        cur_text = "Live: —"
        cur_cli  = None

    cur_badge = Gtk.Label(label=cur_text)
    cur_badge.add_css_class("live-badge")
    cur_badge.set_tooltip_text("Live reading from hardware")
    cur_badge.set_valign(Gtk.Align.CENTER)
    top_box.append(cur_badge)

    if param in pending:
        init_val = float(pending[param])
    elif cur_cli is not None:
        init_val = max(lo, min(hi, cur_cli))
    else:
        init_val = float(meta.get("default", lo))

    calc_step = float(max(int(div), 1))

    adj = Gtk.Adjustment(
        value=init_val,
        lower=lo,
        upper=hi,
        step_increment=calc_step,
        page_increment=calc_step * 10,
        page_size=0,
    )
    slider = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adj)
    slider.set_hexpand(True)
    slider.set_valign(Gtk.Align.CENTER)
    slider.set_draw_value(False)
    slider.set_round_digits(0)
    slider.set_tooltip_text(f"Range: {lo} – {hi} {meta['unit']}")

    scroll_controller = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.BOTH_AXES)
    scroll_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    scroll_controller.connect("scroll", lambda *args: True)
    slider.add_controller(scroll_controller)

    btn_remove = Gtk.Button(icon_name="edit-clear-symbolic")
    btn_remove.add_css_class("flat")
    btn_remove.set_tooltip_text("Remove this setting from startup/boot service (may require reboot to fully clear)")
    btn_remove.set_valign(Gtk.Align.CENTER)
    btn_remove.set_margin_start(4)

    def on_remove(_b, p=param, m=meta, c_cli=cur_cli, sli=slider, low_val=lo):
        is_gfx = p in ("min-gfxclk", "max-gfxclk", "gfx-clk")
        is_co = p == "set-coall" or p.startswith("set-coper-") or p == "set-cogfx"
        
        if is_gfx:
            params_to_remove = ["min-gfxclk", "max-gfxclk", "gfx-clk"]
        elif p == "set-cogfx":
            params_to_remove = ["set-cogfx"]
        elif p == "set-coall" or p.startswith("set-coper-"):
            if app:
                params_to_remove = [k for k in app._slider_rows.keys() if k == "set-coall" or k.startswith("set-coper-")]
            else:
                params_to_remove = [p]
        else:
            params_to_remove = [p]

        was_configured = False
        if app:
            was_configured = any(
                x in getattr(app, "pending_settings", {}) or x in getattr(app, "applied_settings", {})
                for x in params_to_remove
            )

        success, msg = ryzen.remove_settings_from_startup(params_to_remove)
        
        if success:
            if app:
                for x in params_to_remove:
                    if x in getattr(app, "pending_settings", {}):
                        del app.pending_settings[x]
                    if x in getattr(app, "applied_settings", {}):
                        del app.applied_settings[x]
                if is_gfx and was_configured:
                    app.gfx_reboot_required = True

            for x in params_to_remove:
                row_widget = app._slider_rows.get(x) if app else None
                if row_widget:
                    sli_widget = getattr(row_widget, "_slider", None)
                    meta_widget = getattr(row_widget, "_param_meta", None)
                    if sli_widget and meta_widget:
                        c_cli_widget = None
                        vkey = meta_widget["value_key"]
                        cur_raw = app.current_info.get(vkey) if app else None
                        if cur_raw is not None:
                            c_cli_widget = cur_raw * meta_widget["display_divisor"]

                        row_widget._updating_programmatically = True
                        if c_cli_widget is not None:
                            sli_widget.set_value(c_cli_widget)
                        else:
                            sli_widget.set_value(float(meta_widget.get("default", meta_widget["min"])))
                        row_widget._updating_programmatically = False

                        if hasattr(row_widget, "_update_val_label"):
                            row_widget._update_val_label(sli_widget, False)

            if app and hasattr(app, "_update_conflicts"):
                app._update_conflicts()

            if app and app.win:
                if was_configured:
                    if is_gfx:
                        heading = "Graphics Clock Overrides Cleared"
                        body = "All graphics clock options have been cleared from startup settings.\n\nA reboot is recommended to fully return the graphics system to stock firmware behavior."
                    elif is_co:
                        heading = "Curve Optimizer Cleared"
                        body = "All Curve Optimizer settings (Global & Per Core) have been cleared.\n\nA reboot is recommended to fully clear these settings from hardware."
                    else:
                        heading = "Setting Removed from Startup"
                        body = f"{msg}\n\nA reboot is recommended to fully clear this setting from hardware."
                    
                    reboot_dialog = Adw.MessageDialog(
                        transient_for=app.win,
                        heading=heading,
                        body=body,
                    )
                    reboot_dialog.add_response("later", "Later")
                    reboot_dialog.add_response("reboot", "Reboot Now")
                    reboot_dialog.set_default_response("reboot")
                    reboot_dialog.set_response_appearance("reboot", Adw.ResponseAppearance.SUGGESTED)

                    def on_reboot_response(d, response):
                        if response == "reboot":
                            subprocess.run(["pkexec", "systemctl", "reboot"], check=False)

                    reboot_dialog.connect("response", on_reboot_response)
                    reboot_dialog.present()
                else:
                    if hasattr(app, "_show_toast"):
                        app._show_toast(f"{param} was not configured in startup settings.", is_error=False)
            else:
                if app and hasattr(app, "_show_toast"):
                    app._show_toast(msg + "\nYou may need to reboot for the hardware to fully clear this setting.", is_error=False)
        else:
            if app and hasattr(app, "_show_toast"):
                app._show_toast(msg, is_error=True)

    btn_remove.connect("clicked", on_remove)
    top_box.append(btn_remove)

    main_box.append(top_box)

    bottom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
    bottom_box.set_margin_top(10)

    unit_label = dunit if dunit else meta["unit"]

    def adjust_slider(direction: int, steps: int):
        delta = max(int(div), 1) * steps
        adj = slider.get_adjustment()
        slider.set_value(max(adj.get_lower(), min(adj.get_upper(), slider.get_value() + direction * delta)))

    def make_step_btn(label: str, direction: int, steps: int, tooltip: str) -> Gtk.Button:
        b = Gtk.Button(label=label)
        b.add_css_class("step-btn")
        b.set_tooltip_text(tooltip)
        b.set_valign(Gtk.Align.CENTER)
        b.connect("clicked", lambda _b: adjust_slider(direction, steps))
        return b

    btn_minus = Gtk.Button(icon_name="list-remove-symbolic")
    btn_minus.add_css_class("circular")
    btn_minus.add_css_class("flat")
    btn_minus.add_css_class("adj-btn")
    btn_minus.set_tooltip_text(f"−1 {unit_label}")
    btn_minus.set_valign(Gtk.Align.CENTER)
    btn_minus.connect("clicked", lambda _b: adjust_slider(-1, 1))

    btn_plus = Gtk.Button(icon_name="list-add-symbolic")
    btn_plus.add_css_class("circular")
    btn_plus.add_css_class("flat")
    btn_plus.add_css_class("adj-btn")
    btn_plus.set_tooltip_text(f"+1 {unit_label}")
    btn_plus.set_valign(Gtk.Align.CENTER)
    btn_plus.connect("clicked", lambda _b: adjust_slider(1, 1))

    btn_minus_100 = make_step_btn("−100", -1, 100, f"−100 {unit_label}")
    btn_minus_10  = make_step_btn("−10",  -1,  10, f"−10 {unit_label}")
    btn_plus_10   = make_step_btn("+10",   1,  10, f"+10 {unit_label}")
    btn_plus_100  = make_step_btn("+100",  1, 100, f"+100 {unit_label}")

    target_badge = Gtk.Label()
    target_badge.add_css_class("target-badge")
    target_badge.set_valign(Gtk.Align.CENTER)
    target_badge.set_size_request(100, -1)

    row._updating_programmatically = False

    def update_val_label(scale, user_triggered=False):
        if getattr(row, "_updating_programmatically", False):
            return
        v = scale.get_value()
        if user_triggered or param in pending:
            target_badge.set_text(f"Target: {_fmt(v, div, dunit)}")
            pending[param] = int(v)
        else:
            target_badge.set_text("Target: Auto")

        if app and hasattr(app, "_update_conflicts"):
            app._update_conflicts()

    slider.connect("value-changed", lambda s: update_val_label(s, True))
    row._update_val_label = update_val_label
    update_val_label(slider, False)

    bottom_box.append(btn_minus_100)
    bottom_box.append(btn_minus_10)
    bottom_box.append(btn_minus)
    bottom_box.append(slider)
    bottom_box.append(btn_plus)
    bottom_box.append(btn_plus_10)
    bottom_box.append(btn_plus_100)
    bottom_box.append(target_badge)
    
    main_box.append(bottom_box)
    row.set_child(main_box)

    if not is_supported:
        row.set_sensitive(False)

    row._slider     = slider
    row._cur_badge  = cur_badge
    row._param_meta = meta
    row._desc_label = desc_label
    row._bottom_box = bottom_box

    return row


def _build_monitor_card(val_key: str, lim_key: str | None, label: str, unit: str, icon_name: str, current_info: dict) -> Gtk.Box:
    """Build a monitor statistics card with progress bar"""
    val   = current_info.get(val_key)
    limit = current_info.get(lim_key) if lim_key else None

    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    card.add_css_class("monitor-card")
    card.set_hexpand(True)

    top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    top_row.set_hexpand(True)

    icon = Gtk.Image.new_from_icon_name(icon_name)
    icon.add_css_class("monitor-icon")
    top_row.append(icon)

    name_lbl = Gtk.Label(label=label)
    name_lbl.add_css_class("monitor-name-label")
    name_lbl.set_halign(Gtk.Align.START)
    name_lbl.set_hexpand(True)
    top_row.append(name_lbl)

    limit_str = _fmt_limit(limit, unit)
    lim_lbl = Gtk.Label(label=limit_str)
    lim_lbl.add_css_class("monitor-limit-badge")
    lim_lbl.set_halign(Gtk.Align.END)
    top_row.append(lim_lbl)

    card.append(top_row)

    val_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    val_row.set_halign(Gtk.Align.START)
    val_row.set_margin_top(8)

    val_str = f"{val:.1f}" if val is not None else "—"
    val_lbl = Gtk.Label(label=val_str)
    val_lbl.add_css_class("monitor-value-label")
    val_row.append(val_lbl)

    unit_lbl = Gtk.Label(label=unit)
    unit_lbl.add_css_class("monitor-unit-label")
    unit_lbl.set_valign(Gtk.Align.END)
    unit_lbl.set_margin_bottom(6)
    val_row.append(unit_lbl)
    card.append(val_row)

    fraction = 0.0
    if val is not None and limit and limit > 0:
        fraction = min(1.0, val / limit)

    bar = Gtk.ProgressBar()
    bar.add_css_class("usage-bar")
    bar.set_fraction(fraction)
    bar.add_css_class(_bar_class(fraction))
    card.append(bar)

    card._val_lbl   = val_lbl
    card._lim_lbl   = lim_lbl
    card._bar       = bar
    card._val_key   = val_key
    card._lim_key   = lim_key
    card._unit      = unit

    return card


def _make_card_grid(app, defs: list[tuple]) -> Gtk.Grid:
    """Arrange monitor cards inside a grid layout"""
    grid = Gtk.Grid()
    grid.set_column_homogeneous(True)
    grid.set_row_homogeneous(False)
    grid.set_column_spacing(16)
    grid.set_row_spacing(16)
    grid.set_margin_bottom(12)

    count = len(defs)

    for i, (val_key, lim_key, label, unit, icon_name) in enumerate(defs):
        card = _build_monitor_card(val_key, lim_key, label, unit, icon_name, app.current_info)
        app._dashboard_cards.append(card)

        if count == 4:
            col = i % 2
            row = i // 2
            grid.attach(card, col, row, 1, 1)
        elif count == 3:
            if i < 2:
                grid.attach(card, i, 0, 1, 1)
            else:
                grid.attach(card, 0, 1, 2, 1)
        elif count == 2:
            grid.attach(card, 0, i, 2, 1)
        else:
            grid.attach(card, 0, i, 2, 1)

    return grid


def _build_section_header(title: str, icon_name: str) -> Gtk.Box:
    """Create a section header with an icon"""
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    box.add_css_class("section-title-box")

    icon = Gtk.Image.new_from_icon_name(icon_name)
    icon.add_css_class("category-icon")
    box.append(icon)

    label = Gtk.Label(label=title)
    label.add_css_class("section-title-label")
    box.append(label)

    return box
