import logging
import threading
import time
import subprocess
from gi.repository import Adw, GLib
import ryzen

log = logging.getLogger(__name__)


class ActionsMixin:
    """App action callbacks and user event handlers"""

    def on_apply_clicked(self, _btn) -> None:
        """Apply button click handler (shows a warning dialog if tuning parameters look extreme)"""
        # Check which settings changed since we last wrote to hardware
        diff_settings = {}
        for k, v in self.pending_settings.items():
            if self.applied_settings.get(k) != v:
                diff_settings[k] = v

        if not diff_settings:
            self._show_toast("No changes to apply.", is_error=False)
            return

        # Build list of settings to show in warning dialog
        risky_params = []
        for param in diff_settings:
            if param.startswith("set-co"):
                risky_params.append(f"Curve Optimizer ({param})")
            if param in ("oc-clk", "oc-volt"):
                risky_params.append(f"Manual Overclock ({param})")

        # Warn user if power limits are set very high (above 100W)
        for param, val in diff_settings.items():
            if param.endswith("-limit") and val > 100000:
                risky_params.append(f"High Power Limit ({param}: {val/1000:.1f}W)")

        msg = "Are you sure you want to apply these settings to hardware?"
        if risky_params:
            risky_list = "\n • ".join(risky_params)
            msg = f"<b>Risky settings detected:</b>\n • {risky_list}\n\nAggressive tuning may cause system instability or hardware stress. Continue?"

        dialog = Adw.MessageDialog(
            transient_for=self.win,
            heading="Apply Hardware Settings?",
            body=msg,
        )
        dialog.set_body_use_markup(True)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("apply", "Apply")
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.set_response_appearance("apply", Adw.ResponseAppearance.SUGGESTED)

        def on_response(d, response):
            if response == "apply":
                self._execute_apply(diff_settings)

        dialog.connect("response", on_response)
        dialog.present()

    def _execute_apply(self, diff_settings: dict) -> None:
        self._set_actions_sensitive(False)
        self.btn_apply.set_label("Applying…")

        def do_apply():
            ok, msg = ryzen.apply_settings(diff_settings, self.supported_params, self.cpu_family)
            GLib.idle_add(self._on_apply_done, ok, msg, diff_settings)

        t = threading.Thread(target=do_apply, daemon=True)
        t.start()

    def _on_apply_done(self, ok: bool, msg: str, applied_diff: dict) -> bool:
        self._set_actions_sensitive(True)
        self.btn_apply.set_label("Apply Settings")
        self._show_toast(msg, is_error=not ok)
        if ok:
            # Update local successfully-applied state tracking upon success
            self.applied_settings.update(applied_diff)
            # Refresh to reflect new state
            GLib.timeout_add(500, lambda: self._do_refresh_async(force_sync_sliders=False) or False)
        else:
            # Sync sliders and pending_settings back to actual hardware/saved values to clear poisoned/unsupported states
            GLib.timeout_add(500, lambda: self._do_refresh_async(force_sync_sliders=True) or False)
        return False

    # ── Presets ────────────────────────────────────────────────────────────────

    def on_power_saving_clicked(self, _btn) -> None:
        self._set_actions_sensitive(False)
        def go():
            ok, msg = ryzen.apply_preset("power-saving")
            GLib.idle_add(self._on_preset_done, ok, msg)
        threading.Thread(target=go, daemon=True).start()

    def on_max_performance_clicked(self, _btn) -> None:
        self._set_actions_sensitive(False)
        def go():
            ok, msg = ryzen.apply_preset("max-performance")
            GLib.idle_add(self._on_preset_done, ok, msg)
        threading.Thread(target=go, daemon=True).start()

    def _on_preset_done(self, ok: bool, msg: str) -> bool:
        self._set_actions_sensitive(True)
        self._show_toast(msg, is_error=not ok)
        if ok:
            GLib.timeout_add(500, lambda: self._do_refresh_async(force_sync_sliders=True) or False)
        return False

    # ── Startup Service Toggle ──────────────────────────────────────────────────

    def on_startup_switch_toggled(self, switch_row, _spec) -> None:
        if getattr(self, "_setting_service_switch", False):
            return
        active = switch_row.get_active()
        if active != ryzen.is_service_enabled():
            # Disable switch to prevent rapid clicking of systemctl commands
            switch_row.set_sensitive(False)

            def run_toggle():
                start_time = time.time()
                ok, msg = ryzen.set_service_enabled(active)

                # Sleep 1.5s to let systemd finish its tasks before user clicks again
                elapsed = time.time() - start_time
                cooldown = 1.5
                if elapsed < cooldown:
                    time.sleep(cooldown - elapsed)

                GLib.idle_add(self._on_startup_toggle_done, ok, msg, active, switch_row)
            threading.Thread(target=run_toggle, daemon=True).start()

    def _on_startup_toggle_done(self, ok: bool, msg: str, active: bool, switch_row) -> bool:
        self._show_toast(msg, is_error=not ok)
        if not ok:
            self._setting_service_switch = True
            switch_row.set_active(not active)
            self._setting_service_switch = False
        # Turn the row back on after cool down
        switch_row.set_sensitive(True)
        return False

    # ── Factory Reset ──────────────────────────────────────────────────────────

    def on_factory_reset_clicked(self, _btn) -> None:
        dialog = Adw.MessageDialog(
            transient_for=self.win,
            heading="Factory Reset & Wipe?",
            body="This will:\n • Delete all saved settings\n • Disable the boot-apply service\n • Clear all overrides on the next reboot\n\nAre you sure you want to proceed?",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("reset", "Reset Everything")
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)

        def on_response(d, response):
            if response == "reset":
                self._execute_factory_reset()

        dialog.connect("response", on_response)
        dialog.present()

    def _execute_factory_reset(self) -> None:
        self._set_actions_sensitive(False)
        def do_reset():
            ok, msg = ryzen.factory_reset()
            GLib.idle_add(self._on_factory_reset_done, ok, msg)
        threading.Thread(target=do_reset, daemon=True).start()

    def _on_factory_reset_done(self, ok: bool, msg: str) -> bool:
        self._set_actions_sensitive(True)
        if ok:
            # Flag reboot if min/max graphics clocks were altered
            had_gfx = any(
                p in self.applied_settings
                for p in ("min-gfxclk", "max-gfxclk", "gfx-clk")
            )
            self.pending_settings.clear()
            self.applied_settings.clear()
            if had_gfx:
                self.gfx_reboot_required = True

            # Prompt user to reboot immediately
            reboot_dialog = Adw.MessageDialog(
                transient_for=self.win,
                heading="Reset Complete",
                body="Settings have been wiped. A system reboot is required to clear current hardware registers and return to stock behavior.\n\nWould you like to reboot now?",
            )
            reboot_dialog.add_response("later", "Later")
            reboot_dialog.add_response("reboot", "Reboot Now")
            reboot_dialog.set_default_response("reboot")
            reboot_dialog.set_response_appearance("reboot", Adw.ResponseAppearance.SUGGESTED)

            def on_reboot_response(d, response):
                if response == "reboot":
                    subprocess.run(["pkexec", "systemctl", "reboot"], check=False)
                else:
                    self.on_refresh_clicked(None)

            reboot_dialog.connect("response", on_reboot_response)
            reboot_dialog.present()
        else:
            self._show_toast(f"Reset failed: {msg}", is_error=True)
        return False

    # ── Enthusiast Mode Toggle ──────────────────────────────────────────────────

    def on_enthusiast_toggled(self, switch_row, _spec) -> None:
        active = switch_row.get_active()
        if self.enthusiast_mode == active:
            return
        self.enthusiast_mode = active
        self.ui_settings["enthusiast_mode"] = active
        self._save_ui_settings()

        # High limits for Enthusiast Mode
        power_standard_max = 130000
        power_enthusiast_max = 250000  # 250W

        current_standard_max = 300000
        current_enthusiast_max = 500000  # 500A

        for param, row in self._slider_rows.items():
            meta = getattr(row, "_param_meta", None)
            if not meta:
                continue

            # Determine the new max range
            if meta["category"] == "power" or meta["param"] == "skin-temp-limit":
                new_max = power_enthusiast_max if active else power_standard_max
            elif meta["category"] == "current":
                if meta["param"] in ("vrm-current", "vrmmax-current"):
                    new_max = current_enthusiast_max if active else current_standard_max
                else:
                    new_max = 150000 if active else 100000
            else:
                continue

            # Set new upper boundaries on slider ranges
            slider = getattr(row, "_slider", None)
            if slider:
                adj = slider.get_adjustment()
                val = adj.get_value()
                if not active and val > new_max:
                    adj.set_value(new_max)
                adj.set_upper(new_max)
                slider.set_tooltip_text(f"Range: {int(adj.get_lower())} – {new_max} {meta['unit']}")

                # Sync range metadata so resets don't clamp settings
                meta["max"] = new_max

                row._updating_programmatically = True
                slider.set_value(slider.get_value())  # nudge to force badge refresh
                row._updating_programmatically = False
                if hasattr(row, "_update_val_label"):
                    row._update_val_label(slider, False)

        if active:
            self._show_toast("Enthusiast Mode: Extreme limits unlocked up to 250W!", is_error=False)
        else:
            self._show_toast("Enthusiast Mode: Reset ranges back to standard bounds.", is_error=False)

    def _update_conflicts(self) -> None:
        """Lock out conflicting settings (GFX min/max vs forced, CO all vs per-core)"""
        
        # 1. GFX Clocks
        if getattr(self, "gfx_reboot_required", False):
            # Lock everything if GFX was reset to stock and system needs a reboot
            for param in ("min-gfxclk", "max-gfxclk", "gfx-clk"):
                row = self._slider_rows.get(param)
                if not row:
                    continue
                meta = getattr(row, "_param_meta", None)
                desc_label = getattr(row, "_desc_label", None)
                if not meta or not desc_label:
                    continue

                hw_supported = ryzen.is_parameter_supported(param, self.cpu_family, self.supported_params)
                if not hw_supported:
                    row.set_sensitive(False)
                    desc_label.set_markup(f"<span style='italic' size='small'>{meta['desc']} <span color='#e01b24' weight='bold' size='small'>(Unsupported on this CPU)</span></span>")
                    continue

                row._bottom_box.set_sensitive(False)
                desc_label.set_markup(f"<span style='italic' size='small'>{meta['desc']} <span color='#e01b24' weight='bold' size='small'>(Unsupported: reboot required to clear GFX conflicts)</span></span>")
        else:
            has_min_max = ("min-gfxclk" in self.pending_settings) or ("max-gfxclk" in self.pending_settings)
            has_forced = "gfx-clk" in self.pending_settings

            for param in ("min-gfxclk", "max-gfxclk", "gfx-clk"):
                row = self._slider_rows.get(param)
                if not row:
                    continue
                meta = getattr(row, "_param_meta", None)
                desc_label = getattr(row, "_desc_label", None)
                if not meta or not desc_label:
                    continue

                hw_supported = ryzen.is_parameter_supported(param, self.cpu_family, self.supported_params)
                if not hw_supported:
                    row.set_sensitive(False)
                    desc_label.set_markup(f"<span style='italic' size='small'>{meta['desc']} <span color='#e01b24' weight='bold' size='small'>(Unsupported on this CPU)</span></span>")
                    continue

                is_conflicted = False
                conflict_msg = ""
                if param in ("min-gfxclk", "max-gfxclk") and has_forced:
                    is_conflicted = True
                    conflict_msg = "conflicts with Forced iGPU Clock"
                elif param == "gfx-clk" and has_min_max:
                    is_conflicted = True
                    conflict_msg = "conflicts with min/max iGPU Clock"

                if is_conflicted:
                    row._bottom_box.set_sensitive(False)
                    desc_label.set_markup(f"<span style='italic' size='small'>{meta['desc']} <span color='#e01b24' weight='bold' size='small'>(Unsupported: {conflict_msg})</span></span>")
                else:
                    row.set_sensitive(True)
                    row._bottom_box.set_sensitive(True)
                    desc_text = meta["desc"]
                    if param in ("min-gfxclk", "max-gfxclk"):
                        ryzenadj_native = param in (self.supported_params or set())
                        if not ryzenadj_native and ryzen.is_sysfs_gfx_clk_available():
                            desc_text = f"{desc_text} <span color='#30d158' weight='bold' size='small'>(AMDGPU Sysfs Overdrive - fallback)</span>"
                    desc_label.set_markup(f"<span style='italic' size='small'>{desc_text}</span>")

        # 2. Curve Optimizer (All Core vs Per Core)
        co_params = [p for p in self._slider_rows.keys() if p == "set-coall" or p.startswith("set-coper-")]
        has_coall = "set-coall" in self.pending_settings
        has_coper = any(p.startswith("set-coper-") for p in self.pending_settings)

        for param in co_params:
            row = self._slider_rows.get(param)
            if not row:
                continue
            meta = getattr(row, "_param_meta", None)
            desc_label = getattr(row, "_desc_label", None)
            if not meta or not desc_label:
                continue
            
            hw_supported = ryzen.is_parameter_supported(param, self.cpu_family, self.supported_params)
            if not hw_supported:
                row.set_sensitive(False)
                desc_label.set_markup(f"<span style='italic' size='small'>{meta['desc']} <span color='#e01b24' weight='bold' size='small'>(Unsupported on this CPU)</span></span>")
                continue

            is_conflicted = False
            conflict_msg = ""
            if param.startswith("set-coper-") and has_coall:
                is_conflicted = True
                conflict_msg = "conflicts with All Core Offset"
            elif param == "set-coall" and has_coper:
                is_conflicted = True
                conflict_msg = "conflicts with Per Core Offsets"

            if is_conflicted:
                row._bottom_box.set_sensitive(False)
                desc_label.set_markup(f"<span style='italic' size='small'>{meta['desc']} <span color='#e01b24' weight='bold' size='small'>(Unsupported: {conflict_msg})</span></span>")
            else:
                row.set_sensitive(True)
                row._bottom_box.set_sensitive(True)
                desc_label.set_markup(f"<span style='italic' size='small'>{meta['desc']}</span>")
