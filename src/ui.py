"""Main application window layout"""
import init_gi
import ryzen

from gi.repository import Gtk, Adw, Gio, GObject

# Import widgets and pages to orchestrate the main window layout
from widgets import (
    get_cpu_name,
    _fmt_limit,
    _fmt,
    _bar_class
)


from pages import (
    build_dependency_missing_page,
    build_auth_required_page,
    _build_dashboard_page,
    _build_profiles_page,
    _build_slider_page,
    _build_settings_page
)


def build_main_window(app) -> Adw.ApplicationWindow:
    """Build the main app window and set up pages"""
    win = Adw.ApplicationWindow(application=app)
    win.set_default_size(1050, 780)
    win.set_title("Ryzenadj-gtk")
    win.add_css_class("ryzenadj-win")

    # Refresh button
    app.btn_refresh = Gtk.Button(icon_name="view-refresh-symbolic")
    app.btn_refresh.set_tooltip_text("Refresh readings (F5)")
    app.btn_refresh.connect("clicked", app.on_refresh_clicked)

    # Menu button
    app.menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic")
    app.menu_btn.set_tooltip_text("Menu")

    # View stack
    view_stack = Adw.ViewStack()
    view_stack.set_vexpand(True)
    app.view_stack = view_stack

    # Dashboard page
    dashboard_page = _build_dashboard_page(app)
    view_stack.add_titled_with_icon(
        dashboard_page, "dashboard", "Dashboard",
        "utilities-system-monitor-symbolic"
    )

    # Profiles page
    profiles_page = _build_profiles_page(app)
    view_stack.add_titled_with_icon(
        profiles_page, "profiles", "Profiles", "user-bookmarks-symbolic"
    )

    # Power page
    power_params = [m for m in ryzen.SETTINGS_PARAMS if m["category"] == "power"]
    timing_params = [m for m in ryzen.SETTINGS_PARAMS if m["category"] == "timing"]
    power_page = _build_slider_page(
        app, "Power", "battery-symbolic", "power",
        [
            ("Power Limits", "STAPM and PPT power envelope — values in mW, shown in W", power_params),
            ("Time Constants", "STAPM and Slow PPT averaging windows (seconds)", timing_params)
        ]
    )
    view_stack.add_titled_with_icon(
        power_page, "power", "Power", "battery-symbolic"
    )

    # Clocks page
    clocks_params = [m for m in ryzen.SETTINGS_PARAMS if m["category"] == "clocks"]
    clocks_page = _build_slider_page(
        app, "Clocks", "system-run-symbolic", "clocks",
        [("Clockspeed Limits", "Manual overclock limits and engine frequency boundaries (MHz)", clocks_params)]
    )
    view_stack.add_titled_with_icon(
        clocks_page, "clocks", "Clocks", "system-run-symbolic"
    )

    # Current page
    current_params = [m for m in ryzen.SETTINGS_PARAMS if m["category"] == "current"]
    current_page = _build_slider_page(
        app, "Current", "thunderbolt-symbolic", "current",
        [("Current Limits", "TDC and EDC current envelope — values in mA, shown in A", current_params)]
    )
    view_stack.add_titled_with_icon(
        current_page, "current", "Current", "thunderbolt-symbolic"
    )

    # Thermal page
    thermal_params = [m for m in ryzen.SETTINGS_PARAMS if m["category"] == "thermal"]
    thermal_page = _build_slider_page(
        app, "Thermal", "display-brightness-symbolic", "thermal",
        [("Temperature Limits", "CPU and skin temperature ceilings (°C)", thermal_params)]
    )
    view_stack.add_titled_with_icon(
        thermal_page, "thermal", "Thermal", "display-brightness-symbolic"
    )

    # Undervolt page
    undervolt_params = [m for m in ryzen.SETTINGS_PARAMS if m["category"] == "undervolt"]
    co_global = [m for m in undervolt_params if m["param"] in ("set-coall", "set-cogfx")]
    co_per_core = [m for m in undervolt_params if m["param"].startswith("set-coper-")]
    
    undervolt_page = _build_slider_page(
        app, "Undervolt", "cpu-symbolic", "undervolt",
        [
            ("Global Curve Optimizer", "All-core and integrated GPU offset (negative for undervolt, positive for overvolt)", co_global),
            ("Per Core Curve Optimizer", "Individual CPU core offsets", co_per_core)
        ]
    )
    view_stack.add_titled_with_icon(
        undervolt_page, "undervolt", "Undervolt", "computer-symbolic"
    )

    # Settings page
    settings_page = _build_settings_page(app)
    view_stack.add_titled_with_icon(
        settings_page, "settings", "Settings", "preferences-system-symbolic"
    )

    # Sidebar Split View
    split_view = Adw.OverlaySplitView()
    split_view.set_sidebar_position(Gtk.PackType.START)
    split_view.set_min_sidebar_width(180)
    split_view.set_max_sidebar_width(240)
    split_view.set_sidebar_width_fraction(0.20)
    split_view.set_show_sidebar(True)

    # Sidebar layout
    sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    sidebar_box.add_css_class("sidebar-pane")
    sidebar_header = Adw.HeaderBar()
    sidebar_header.add_css_class("sidebar-header")
    sidebar_header.set_show_end_title_buttons(False)

    sidebar_title = Gtk.Label(label="Ryzenadj-gtk")
    sidebar_title.add_css_class("title")
    sidebar_title.add_css_class("bold")
    sidebar_header.set_title_widget(sidebar_title)
    sidebar_header.pack_end(app.menu_btn)
    sidebar_box.append(sidebar_header)

    sidebar_navigation = Adw.ViewSwitcherSidebar()
    sidebar_navigation.add_css_class("navigation-sidebar")
    sidebar_navigation.set_stack(view_stack)

    sidebar_scrolled = Gtk.ScrolledWindow()
    sidebar_scrolled.set_vexpand(True)
    sidebar_scrolled.set_child(sidebar_navigation)
    sidebar_box.append(sidebar_scrolled)

    split_view.set_sidebar(sidebar_box)

    # Main Content Area
    content_toolbar_view = Adw.ToolbarView()
    content_header = Adw.HeaderBar()
    content_header.add_css_class("main-header")

    # Toggle sidebar button
    app.btn_sidebar = Gtk.ToggleButton(icon_name="sidebar-show-symbolic")
    app.btn_sidebar.set_active(True)
    app.btn_sidebar.set_tooltip_text("Toggle Sidebar")
    app.btn_sidebar.connect("toggled", lambda b: split_view.set_show_sidebar(b.get_active()))
    content_header.pack_start(app.btn_sidebar)

    split_view.bind_property("show-sidebar", app.btn_sidebar, "active", GObject.BindingFlags.BIDIRECTIONAL)

    # Title widget
    app.window_title = Adw.WindowTitle()
    app.window_title.set_title("Dashboard")
    app.window_title.set_subtitle(get_cpu_name())
    content_header.set_title_widget(app.window_title)

    def update_header_title(stack, _paramspec):
        child = stack.get_visible_child()
        if child:
            title = ""
            if hasattr(child, "get_title"):
                title = child.get_title()
            elif isinstance(child, Gtk.ScrolledWindow) and child.get_name() == "dashboard":
                title = "Dashboard"
            app.window_title.set_title(title)
    view_stack.connect("notify::visible-child", update_header_title)

    content_header.pack_end(app.btn_refresh)
    content_toolbar_view.add_top_bar(content_header)
    content_toolbar_view.set_content(view_stack)

    # Action Bar Presets
    action_bar = Gtk.ActionBar()
    action_bar.add_css_class("preset-row")

    btn_ps = Gtk.Button(label="⚡ Power Saving")
    btn_ps.add_css_class("preset-btn")
    btn_ps.add_css_class("btn-power-saving")
    btn_ps.set_tooltip_text("Apply ryzenadj --power-saving preset")
    btn_ps.connect("clicked", app.on_power_saving_clicked)

    btn_mp = Gtk.Button(label="🚀 Max Performance")
    btn_mp.add_css_class("preset-btn")
    btn_mp.add_css_class("btn-max-performance")
    btn_mp.set_tooltip_text("Apply ryzenadj --max-performance preset")
    btn_mp.connect("clicked", app.on_max_performance_clicked)

    btn_apply = Gtk.Button(label="Apply Settings")
    btn_apply.add_css_class("apply-btn")
    btn_apply.set_tooltip_text("Write slider values to hardware (Ctrl+S)")
    btn_apply.connect("clicked", app.on_apply_clicked)
    app.btn_apply = btn_apply
    app.btn_ps = btn_ps
    app.btn_mp = btn_mp

    action_bar.pack_start(btn_ps)
    action_bar.pack_start(btn_mp)
    action_bar.pack_end(btn_apply)

    content_toolbar_view.add_bottom_bar(action_bar)
    split_view.set_content(content_toolbar_view)

    toast_overlay = Adw.ToastOverlay()
    toast_overlay.set_child(split_view)
    win.set_content(toast_overlay)
    app.toast_overlay = toast_overlay

    # Main Application Menu
    gmenu = Gio.Menu.new()
    
    theme_menu = Gio.Menu.new()
    theme_menu.append("Adwaita Default", "app.theme-color::default")
    theme_menu.append("Ryzen Red", "app.theme-color::ryzen")
    theme_menu.append("DLSS Green", "app.theme-color::geforce")
    theme_menu.append("14nm+++ Blue", "app.theme-color::intel")
    theme_menu.append("Archbtw Blue", "app.theme-color::arch")
    theme_menu.append("Saints Purple", "app.theme-color::saints")
    theme_menu.append("Noctua Brown", "app.theme-color::noctua")

    section_theme = Gio.Menu.new()
    section_theme.append_submenu("Accent Color", theme_menu)
    gmenu.append_section(None, section_theme)

    section1 = Gio.Menu.new()
    section1.append("Refresh from Hardware", "app.reload")
    gmenu.append_section(None, section1)

    section2 = Gio.Menu.new()
    section2.append("About Ryzenadj-gtk", "app.about")
    gmenu.append_section(None, section2)

    app.menu_btn.set_menu_model(gmenu)

    return win
