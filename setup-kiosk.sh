#!/bin/bash
# =============================================================
# TransLoc Kiosk Setup Script for Raspberry Pi
# =============================================================
# Compatible with: Raspberry Pi OS, DietPi, Ubuntu, and other
# Debian-based distributions using systemd.
#
# Automatically detects desktop vs console environments and
# configures the display accordingly.
#
# Run on your Pi after copying the project files:
#   sudo bash setup-kiosk.sh
# =============================================================

set -e

echo "========================================="
echo " TransLoc Kiosk Setup"
echo "========================================="

if [ "$EUID" -ne 0 ]; then
    echo "Please run as root: sudo bash setup-kiosk.sh"
    exit 1
fi

KIOSK_DIR="$(cd "$(dirname "$0")" && pwd)"
KIOSK_USER="${SUDO_USER:-$(whoami)}"
KIOSK_HOME=$(eval echo "~$KIOSK_USER")

# Detect if a desktop environment is installed
HAS_DESKTOP=false
if dpkg -l | grep -qE 'lxde|xfce|gnome|mate|desktop' 2>/dev/null || [ -d /usr/share/xsessions ]; then
    HAS_DESKTOP=true
fi

echo "Detected OS:      $(grep -s PRETTY_NAME /etc/os-release | cut -d= -f2 | tr -d '"' || echo 'Unknown')"
echo "Environment:       $(if $HAS_DESKTOP; then echo 'Desktop'; else echo 'Console (framebuffer)'; fi)"
echo "Install directory: $KIOSK_DIR"
echo "Service user:      $KIOSK_USER"
echo ""

echo "[1/5] Updating packages..."
apt-get update -qq

echo "[2/5] Installing Python3 and dependencies..."
apt-get install -y python3 python3-pip python3-pygame fonts-dejavu-core
pip3 install flask requests pygame 2>/dev/null || pip3 install --break-system-packages flask requests pygame 2>/dev/null || true

echo "[3/5] Creating server service..."

cat > /etc/systemd/system/transloc-server.service << EOF
[Unit]
Description=TransLoc Kiosk Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$KIOSK_USER
WorkingDirectory=$KIOSK_DIR
ExecStart=/usr/bin/python3 server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable transloc-server.service

if $HAS_DESKTOP; then
    echo "[4/5] Desktop detected — using autostart for display..."

    # Remove systemd display service if it exists from a previous setup
    systemctl stop transloc-display.service 2>/dev/null || true
    systemctl disable transloc-display.service 2>/dev/null || true
    rm -f /etc/systemd/system/transloc-display.service

    # Create autostart entry that runs after the desktop session loads
    AUTOSTART_DIR="$KIOSK_HOME/.config/autostart"
    mkdir -p "$AUTOSTART_DIR"

    cat > "$AUTOSTART_DIR/transloc-display.desktop" << EOF
[Desktop Entry]
Type=Application
Name=TransLoc Kiosk Display
Exec=/usr/bin/python3 $KIOSK_DIR/display.py
Environment=KIOSK_SERVER=http://localhost:3000
X-GNOME-Autostart-enabled=true
EOF

    chown -R "$KIOSK_USER:$KIOSK_USER" "$KIOSK_HOME/.config/autostart"
    echo "  Created autostart entry at $AUTOSTART_DIR/transloc-display.desktop"

else
    echo "[4/5] Console detected — using systemd for display..."

    # Remove desktop autostart if it exists from a previous setup
    rm -f "$KIOSK_HOME/.config/autostart/transloc-display.desktop" 2>/dev/null

    cat > /etc/systemd/system/transloc-display.service << EOF
[Unit]
Description=TransLoc Kiosk Display
After=transloc-server.service
Wants=transloc-server.service

[Service]
Type=simple
User=$KIOSK_USER
WorkingDirectory=$KIOSK_DIR
ExecStartPre=/bin/sleep 3
ExecStart=/usr/bin/python3 display.py
Restart=always
RestartSec=5
Environment=SDL_FBDEV=/dev/fb0
Environment=SDL_NOMOUSE=1
Environment=KIOSK_SERVER=http://localhost:3000

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable transloc-display.service
fi

echo "[5/5] Configuring display..."

# Disable screen blanking (path varies by OS)
CMDLINE=""
for path in /boot/firmware/cmdline.txt /boot/cmdline.txt; do
    if [ -f "$path" ]; then
        CMDLINE="$path"
        break
    fi
done

if [ -n "$CMDLINE" ] && ! grep -q "consoleblank=0" "$CMDLINE" 2>/dev/null; then
    sed -i 's/$/ consoleblank=0/' "$CMDLINE" 2>/dev/null || true
    echo "  Screen blanking disabled via $CMDLINE"
fi

echo 0 > /sys/class/graphics/fbcon/cursor_blink 2>/dev/null || true

echo ""
echo "========================================="
echo " Setup Complete!"
echo "========================================="
echo ""
echo " Server: systemd service (transloc-server)"
if $HAS_DESKTOP; then
    echo " Display: desktop autostart (launches after login)"
    echo ""
    echo " Make sure auto-login to desktop is enabled:"
    echo "   sudo raspi-config -> System Options -> Boot / Auto Login"
else
    echo " Display: systemd service (transloc-display)"
fi
echo ""
echo " Start now:"
echo "   sudo systemctl start transloc-server"
if $HAS_DESKTOP; then
    echo "   python3 $KIOSK_DIR/display.py   (or reboot)"
else
    echo "   sudo systemctl start transloc-display"
fi
echo ""
echo " Or reboot to auto-start everything:"
echo "   sudo reboot"
echo ""
echo " Configure buses from your phone/laptop:"
echo "   http://$(hostname -I | awk '{print $1}'):3000/settings"
echo ""
echo "========================================="
