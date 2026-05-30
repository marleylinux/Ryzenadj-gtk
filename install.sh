#!/bin/bash
# ryzenadj-gtk Installation Script
# Mirrors the PKGBUILD installation logic.
# Run with: sudo ./install.sh

set -e

if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (sudo ./install.sh)"
  exit 1
fi

echo "==> Installing ryzenadj-gtk..."

INSTALL_DIR="/usr/share/ryzenadj-gtk"
BIN_DIR="/usr/bin"
APP_DIR="/usr/share/applications"

# Create directories
mkdir -p "$INSTALL_DIR"
mkdir -p "$APP_DIR"

# python files
echo "  -> Copying Python files and assets..."
cp src/*.py "$INSTALL_DIR/"
cp -r src/assets "$INSTALL_DIR/"
chmod 644 "$INSTALL_DIR"/*.py
chmod 755 "$INSTALL_DIR/app.py"
find "$INSTALL_DIR/assets" -type d -exec chmod 755 {} +
find "$INSTALL_DIR/assets" -type f -exec chmod 644 {} +

# icon (png)
for size in 256 512; do
    ICON_DIR="/usr/share/icons/hicolor/${size}x${size}/apps"
    mkdir -p "$ICON_DIR"
    cp src/assets/com.marley.ryzenadj-gtk.png "$ICON_DIR/com.marley.ryzenadj-gtk.png"
    chmod 644 "$ICON_DIR/com.marley.ryzenadj-gtk.png"
done

# Install desktop entry
echo "  -> Installing .desktop file..."
cp com.marley.ryzenadj-gtk.desktop "$APP_DIR/com.marley.ryzenadj-gtk.desktop"
chmod 644 "$APP_DIR/com.marley.ryzenadj-gtk.desktop"

# Create executable launcher
echo "  -> Creating launcher..."
cat > "$BIN_DIR/ryzenadj-gtk" << EOF
#!/bin/sh
export PYTHONPATH="$INSTALL_DIR:\$PYTHONPATH"
exec python3 "$INSTALL_DIR/app.py" "\$@"
EOF
chmod 755 "$BIN_DIR/ryzenadj-gtk"

# Update caches
update-desktop-database -q 2>/dev/null || true
gtk-update-icon-cache -f -t /usr/share/icons/hicolor 2>/dev/null || true

# Install systemd service
echo "  -> Installing systemd service..."
cp ryzenadj-gtk-apply.service /usr/lib/systemd/system/ryzenadj-gtk-apply.service
chmod 644 /usr/lib/systemd/system/ryzenadj-gtk-apply.service
systemctl daemon-reload

# Configure passwordless sudo drop-in safely (auto setup)
echo "  -> Configuring secure passwordless sudo for ryzenadj & systemctl..."
SUDOERS_FILE="/etc/sudoers.d/ryzenadj-gtk"
TEMP_SUDOERS=$(mktemp)

if [ -n "$SUDO_USER" ]; then
    cat <<EOF > "$TEMP_SUDOERS"
$SUDO_USER ALL=(ALL) NOPASSWD: /usr/bin/ryzenadj
$SUDO_USER ALL=(ALL) NOPASSWD: /usr/local/bin/ryzenadj
$SUDO_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl enable ryzenadj-gtk-apply.service
$SUDO_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl disable ryzenadj-gtk-apply.service
$SUDO_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl enable --now ryzenadj-gtk-apply.service
$SUDO_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl disable --now ryzenadj-gtk-apply.service
$SUDO_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl is-enabled ryzenadj-gtk-apply.service
$SUDO_USER ALL=(ALL) NOPASSWD: /usr/bin/tee /sys/class/drm/card*/device/pp_od_clk_voltage
$SUDO_USER ALL=(ALL) NOPASSWD: /usr/bin/tee /sys/class/drm/card*/device/power_dpm_force_performance_level
EOF
else
    cat <<EOF > "$TEMP_SUDOERS"
ALL ALL=(ALL) NOPASSWD: /usr/bin/ryzenadj
ALL ALL=(ALL) NOPASSWD: /usr/local/bin/ryzenadj
ALL ALL=(ALL) NOPASSWD: /usr/bin/systemctl enable ryzenadj-gtk-apply.service
ALL ALL=(ALL) NOPASSWD: /usr/bin/systemctl disable ryzenadj-gtk-apply.service
ALL ALL=(ALL) NOPASSWD: /usr/bin/systemctl enable --now ryzenadj-gtk-apply.service
ALL ALL=(ALL) NOPASSWD: /usr/bin/systemctl disable --now ryzenadj-gtk-apply.service
ALL ALL=(ALL) NOPASSWD: /usr/bin/systemctl is-enabled ryzenadj-gtk-apply.service
ALL ALL=(ALL) NOPASSWD: /usr/bin/tee /sys/class/drm/card*/device/pp_od_clk_voltage
ALL ALL=(ALL) NOPASSWD: /usr/bin/tee /sys/class/drm/card*/device/power_dpm_force_performance_level
EOF
fi

# Securely validate syntax using visudo before writing
if visudo -cf "$TEMP_SUDOERS" >/dev/null 2>&1; then
    mv "$TEMP_SUDOERS" "$SUDOERS_FILE"
    chmod 440 "$SUDOERS_FILE"
    chown root:root "$SUDOERS_FILE"
    echo "     Sudoers drop-in configured successfully. Changes usually take effect immediately."
    echo "     If you still get prompted for a password, a reboot will ensure everything is active."
else
    rm -f "$TEMP_SUDOERS"
    echo "     WARNING: Sudoers rule validation failed! Passwordless sudo was not configured." >&2
fi

# Create system settings directory and make it writable by SUDO_USER
echo "  -> Creating system config directory..."
mkdir -p /etc/ryzenadj-gtk
if [ -n "$SUDO_USER" ]; then
    chown -R "$SUDO_USER:" /etc/ryzenadj-gtk
fi
chmod 755 /etc/ryzenadj-gtk

echo ""
echo "==> Installation complete!"
echo "    Launch 'Ryzenadj-gtk' from your application menu, or run: ryzenadj-gtk"
echo ""
read -p "Press Enter to exit..."
