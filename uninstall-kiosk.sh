#!/bin/bash
# =============================================================
# TransLoc Kiosk Uninstall Script
# =============================================================
# Removes all services, autostart entries, and project files
# installed by setup-kiosk.sh.
#
# Run on your Pi:
#   sudo bash uninstall-kiosk.sh
# =============================================================

set -e

echo "========================================="
echo " TransLoc Kiosk Uninstall"
echo "========================================="

if [ "$EUID" -ne 0 ]; then
    echo "Please run as root: sudo bash uninstall-kiosk.sh"
    exit 1
fi

KIOSK_DIR="$(cd "$(dirname "$0")" && pwd)"
KIOSK_USER="${SUDO_USER:-$(whoami)}"
KIOSK_HOME=$(eval echo "~$KIOSK_USER")

echo ""
echo "This will remove:"
echo "  - systemd services (transloc-server, transloc-display)"
echo "  - Desktop autostart entry"
echo "  - Project directory: $KIOSK_DIR"
echo ""
read -p "Are you sure? (y/N): " confirm
if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo "[1/4] Stopping and removing services..."

for svc in transloc-server transloc-display; do
    if systemctl is-active --quiet "$svc" 2>/dev/null; then
        systemctl stop "$svc"
        echo "  Stopped $svc"
    fi
    if systemctl is-enabled --quiet "$svc" 2>/dev/null; then
        systemctl disable "$svc"
        echo "  Disabled $svc"
    fi
    if [ -f "/etc/systemd/system/${svc}.service" ]; then
        rm -f "/etc/systemd/system/${svc}.service"
        echo "  Removed /etc/systemd/system/${svc}.service"
    fi
done

systemctl daemon-reload

echo "[2/4] Removing desktop autostart entry..."

AUTOSTART_FILE="$KIOSK_HOME/.config/autostart/transloc-display.desktop"
if [ -f "$AUTOSTART_FILE" ]; then
    rm -f "$AUTOSTART_FILE"
    echo "  Removed $AUTOSTART_FILE"
else
    echo "  No autostart entry found (skipped)"
fi

echo "[3/4] Removing pip packages installed by setup..."

pip3 uninstall -y flask requests pygame 2>/dev/null || \
pip3 uninstall --break-system-packages -y flask requests pygame 2>/dev/null || \
echo "  Could not remove pip packages (may need manual cleanup)"

echo "[4/4] Removing project directory..."

if [ -d "$KIOSK_DIR" ]; then
    rm -rf "$KIOSK_DIR"
    echo "  Removed $KIOSK_DIR"
fi

echo ""
echo "========================================="
echo " Uninstall Complete!"
echo "========================================="
echo ""
echo " All TransLoc Kiosk files and services have been removed."
echo " You may want to reboot: sudo reboot"
echo ""
echo "========================================="
