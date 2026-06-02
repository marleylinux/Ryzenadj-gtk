import logging
import threading
from gi.repository import GLib
import ryzen
import ui as ui_module

log = logging.getLogger(__name__)

# Constants
REFRESH_INTERVAL_MS = 1000


class MonitorMixin:
    """Background hardware monitoring and periodic UI refresh loop"""

    def _start_refresh_timer(self) -> None:
        self._refresh_timer_id = GLib.timeout_add(
            REFRESH_INTERVAL_MS, self._auto_refresh
        )

    def _auto_refresh(self) -> bool:
        """Timer callback that schedules background hardware stats refresh"""
        if self._auth_granted is not True:
            return True  # Keep timer alive; fires again after retry succeeds

        # Monitor power source transition
        self._check_power_source()

        # Check and re-apply settings periodically to make sure they stick
        if self.ui_settings.get("persistence_enabled", False) and self.applied_settings:
            self._persistence_ticks += 1
            interval = int(self.ui_settings.get("persistence_interval", 30))
            if self._persistence_ticks >= interval:
                self._persistence_ticks = 0
                log.info("Persistence Guard: Verifying and re-applying settings: %s", self.applied_settings)
                def run_persistence():
                    ok, msg = ryzen.apply_settings(self.applied_settings, self.supported_params, self.cpu_family)
                    if not ok:
                        log.error("Persistence Guard: Failed to re-apply settings: %s", msg)
                threading.Thread(target=run_persistence, daemon=True).start()
        else:
            self._persistence_ticks = 0

        if not self._refreshing:
            self._do_refresh_async(force_sync_sliders=False)
        return True  # Keep timer alive

    def on_prepare_for_sleep(self, connection, sender_name, object_path, interface_name, signal_name, parameters, user_data):
        """D-Bus signal callback for system sleep and wake events (researched how systemd triggers sleep/wake to make this work)"""
        try:
            is_about_to_sleep = parameters.get_child_value(0).get_boolean()
            if not is_about_to_sleep:
                log.info("System resumed from sleep. Triggering automatic hardware register restoration...")
                GLib.timeout_add(3000, self._restore_after_sleep)
        except Exception as e:
            log.error("Failed to parse PrepareForSleep parameters: %s", e)

    def _restore_after_sleep(self) -> bool:
        """Restore last applied settings on hardware resume from sleep"""
        if self.ui_settings.get("auto_switch", False):
            current_ac = ryzen.is_on_ac_power()
            self.last_ac_state = current_ac
            log.info("System waking up from sleep. Re-applying auto-switch power profile...")
            self._apply_auto_power_profile(current_ac)
            return False

        if not self.applied_settings:
            log.info("No active settings to restore after sleep.")
            return False

        log.info("Re-applying saved configuration to hardware: %s", self.applied_settings)
        def reapply():
            ok, msg = ryzen.apply_settings(self.applied_settings, self.supported_params, self.cpu_family)
            if ok:
                log.info("Successfully restored hardware registers after system sleep.")
                GLib.idle_add(self._show_toast, "Hardware settings automatically restored after sleep.", False)
            else:
                log.error("Failed to restore hardware registers: %s", msg)
                GLib.idle_add(self._show_toast, "Failed to restore hardware settings after sleep.", True)

        threading.Thread(target=reapply, daemon=True).start()
        return False

    def _check_power_source(self) -> None:
        """Check if power source changed (AC vs Battery) and update profile if it did"""
        current_ac = ryzen.is_on_ac_power()
        if self.last_ac_state is None:
            self.last_ac_state = current_ac
            return

        if current_ac != self.last_ac_state:
            self.last_ac_state = current_ac
            log.info("Power supply state changed: connected_to_ac=%s", current_ac)

            if self.ui_settings.get("auto_switch", False):
                self._apply_auto_power_profile(current_ac)

    def _apply_auto_power_profile(self, is_ac: bool) -> None:
        """Apply the profile configured for AC or Battery (researched how to parse power source transitions)"""
        profile_key = "ac_profile" if is_ac else "battery_profile"
        profile_name = self.ui_settings.get(profile_key, "")

        if not profile_name:
            log.info("No profile configured for %s automation.", "AC" if is_ac else "Battery")
            return

        profiles = ryzen.load_profiles()
        source_label = "AC power" if is_ac else "battery"

        if profile_name == "__power_saving__":
            self._show_toast(f"Switched to {source_label}. Applying 'Power Saving' preset...", is_error=False)
            self.on_power_saving_clicked(None)
        elif profile_name == "__max_performance__":
            self._show_toast(f"Switched to {source_label}. Applying 'Max Performance' preset...", is_error=False)
            self.on_max_performance_clicked(None)
        elif profile_name in profiles:
            target_settings = profiles[profile_name]
            self._show_toast(f"Switched to {source_label}. Applying '{profile_name}' profile...", is_error=False)
            self._set_actions_sensitive(False)

            for param, val in target_settings.items():
                self.pending_settings[param] = val
                if param in self._slider_rows:
                    row_widget = self._slider_rows[param]
                    slider = getattr(row_widget, "_slider", None)
                    if slider:
                        row_widget._updating_programmatically = True
                        slider.set_value(float(val))
                        row_widget._updating_programmatically = False
                        if hasattr(row_widget, "_update_val_label"):
                            row_widget._update_val_label(slider, True)

            def run_write():
                ok, msg = ryzen.apply_settings(target_settings, self.supported_params, self.cpu_family, save=False)
                GLib.idle_add(self._on_apply_done, ok, msg, target_settings)
            threading.Thread(target=run_write, daemon=True).start()
        else:
            log.warning("Configured automation profile '%s' was not found in profiles database.", profile_name)

    def on_refresh_clicked(self, _btn) -> None:
        if self._refreshing:
            return
        if self.btn_refresh:
            self.btn_refresh.set_sensitive(False)
        self._do_refresh_async(force_sync_sliders=True)

    def _do_refresh_async(self, force_sync_sliders: bool = False) -> None:
        self._refreshing = True

        def fetch():
            info = ryzen.get_current_info()
            GLib.idle_add(self._on_refresh_done, info, force_sync_sliders)

        t = threading.Thread(target=fetch, daemon=True)
        t.start()

    def _on_refresh_done(self, info: dict, force_sync_sliders: bool = False) -> bool:
        if info:
            self.current_info = info
            if force_sync_sliders:
                self.pending_settings.clear()
                saved = ryzen.load_settings()
                if saved:
                    self.pending_settings.update(saved)
                self._sync_sliders_to_hardware_or_pending(info, use_pending=True)
                self.applied_settings = dict(self.pending_settings)

        self._refreshing = False

        if self.btn_refresh:
            self.btn_refresh.set_sensitive(True)

        self._update_dashboard_cards()
        self._update_slider_badges()
        self._update_status_label()
        self._update_conflicts()
        return False

    def _update_dashboard_cards(self) -> None:
        for card in self._dashboard_cards:
            val_key = getattr(card, "_val_key", None)
            lim_key = getattr(card, "_lim_key", None)
            if not val_key:
                continue
            val = self.current_info.get(val_key)
            limit = self.current_info.get(lim_key) if lim_key else None

            val_str = f"{val:.1f}" if val is not None else "—"
            card._val_lbl.set_text(val_str)

            if val is not None and limit and limit > 0:
                frac = min(1.0, val / limit)
            else:
                frac = 0.0

            if hasattr(card, "_lim_lbl") and card._lim_lbl:
                card._lim_lbl.remove_css_class("bottleneck")
                limit_str = ui_module._fmt_limit(limit, card._unit)
                if frac >= 0.95:
                    limit_str = f"⚠️ CAPPED ({limit_str.replace('Limit: ', '')})"
                    card._lim_lbl.add_css_class("bottleneck")
                card._lim_lbl.set_text(limit_str)

            bar = card._bar
            for cls in ("low", "medium", "high", "bottleneck"):
                bar.remove_css_class(cls)
            bar.add_css_class(ui_module._bar_class(frac))
            if frac >= 0.95:
                bar.add_css_class("bottleneck")
            bar.set_fraction(frac)

    def _update_slider_badges(self) -> None:
        for param, row in self._slider_rows.items():
            meta = getattr(row, "_param_meta", None)
            if not meta:
                continue
            vkey = meta["value_key"]
            raw = self.current_info.get(vkey)
            if raw is not None:
                cur_text = ui_module._fmt(raw, 1, meta["display_unit"])
            else:
                cur_text = "—"
            badge = getattr(row, "_cur_badge", None)
            if badge:
                badge.set_text(f"Live: {cur_text}")

    def _update_status_label(self) -> None:
        if self.window_title:
            self.window_title.set_subtitle(ui_module.get_cpu_name())
