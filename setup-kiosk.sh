#!/bin/bash
# =============================================================
# TransLoc Kiosk Setup Script for Raspberry Pi
# =============================================================
# Compatible with: Raspberry Pi OS, DietPi, Ubuntu, and other
# Debian-based distributions using systemd.
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

echo "Detected OS: $(grep -s PRETTY_NAME /etc/os-release | cut -d= -f2 | tr -d '\"' || echo 'Unknown')"
echo "Install directory: $KIOSK_DIR"
echo "Service user: $KIOSK_USER"
echo ""

echo "[1/5] Updating packages..."
apt-get update -qq

echo "[2/5] Installing Python3 and dependencies..."
apt-get install -y python3 python3-pip python3-pygame
pip3 install flask requests pygame 2>/dev/null || true

echo "[3/5] Creating systemd services..."

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
systemctl enable transloc-server.service
systemctl enable transloc-display.service

echo "[4/5] Configuring display..."

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

echo "[5/5] Done!"
echo ""
echo "========================================="
echo " Setup Complete!"
echo "========================================="
echo ""
echo " Services installed:"
echo "   transloc-server  - Flask server (port 3000)"
echo "   transloc-display - Pygame kiosk display"
echo ""
echo " Start now:"
echo "   sudo systemctl start transloc-server"
echo "   sudo systemctl start transloc-display"
echo ""
echo " Or reboot to auto-start:"
echo "   sudo reboot"
echo ""
echo " Configure buses from your phone/laptop:"
echo "   http://$(hostname -I | awk '{print $1}'):3000/settings"
echo ""
echo "========================================="
