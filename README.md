# TransLoc Bus Tracker Kiosk

A privacy-first, ad-free bus tracking kiosk for **Raspberry Pi** with an 800x480 display. Uses the TransLoc public API for real-time bus arrivals, vehicle load, and integrates weather-based clothing suggestions.

![Stack: Python + Pygame + Flask](https://img.shields.io/badge/stack-Python%20%2B%20Pygame%20%2B%20Flask-blue)
![Display: 800x480](https://img.shields.io/badge/display-800×480-green)
![Privacy: No tracking](https://img.shields.io/badge/privacy-no%20tracking-brightgreen)

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Raspberry Pi                         │
│                                                         │
│  ┌──────────────┐     ┌──────────────────────────────┐  │
│  │  Flask       │     │  Pygame Display              │  │
│  │  Python      │◄────│  800×480 framebuffer         │  │
│  │  Port 3000   │     │  2×2 bus card grid           │  │
│  └──────┬───────┘     └──────────────────────────────┘  │
│         │                                               │
│         ├──► TransLoc API (bus data)                    │
│         ├──► Open-Meteo API (weather)                   │
│         └──► config.json (saved buses)                  │
└─────────────────────────────────────────────────────────┘

  Your phone/laptop ──► http://pi-ip:3000/settings
```

- **Flask** handles API proxying, caching (10s TTL), and config persistence
- **Pygame** renders directly to the framebuffer — no browser, no desktop, ~75MB RAM total
- **Settings** web page is accessed from your phone or laptop, not on the Pi's screen

## Features

- **4 bus cards** showing route name, stop, ETA countdown, and passenger load
- **Weather widget** with temperature-based clothing suggestions
- **Auto-refresh** every 30 seconds
- **Custom colors** and descriptions per bus
- **Phone-friendly settings** page for configuration
- **Privacy-first** — no ads, no analytics, no user tracking
- **Pi optimized** — 75MB RAM, 15 FPS, no browser needed

## Supported Platforms

This project runs on any **Debian-based Linux** distribution for Raspberry Pi:

| OS | Tested | Notes |
|----|--------|-------|
| Raspberry Pi OS (Raspbian) | Yes | Recommended for most users |
| DietPi | Yes | Lightweight, great for Pi 2 |
| Ubuntu Server | Yes | Uses `/boot/firmware/cmdline.txt` |

It also runs on **macOS** and **Linux desktops** in windowed mode for development.

## Quick Start

### Prerequisites
- Python 3.8+
- pip

### Setup

```bash
# Install Python dependencies
pip3 install flask pygame requests

# Start both server and display
python3 start.py
```

`start.py` launches the Flask server and the Pygame display together. It waits for the server to be ready before starting the display, and shuts both down cleanly on exit.

You can also run them separately if needed:

```bash
python3 server.py &     # Start the server in the background
python3 display.py      # Start the display
```

The display opens an 800x480 window. Configure buses at `http://localhost:3000/settings`.

### Controls

| Key | Action |
|-----|--------|
| `R` | Manual refresh |
| `Q` / `Esc` | Quit display |
| `S` | Print settings URL |
| Click "Refresh" | Manual refresh (bottom-left) |

## Deploy to Raspberry Pi

The following example uses DietPi, but the steps are the same for Raspberry Pi OS, Ubuntu, or any other Debian-based distribution.

### 1. Flash your OS

Download your preferred OS and flash it to your SD card:
- [Raspberry Pi OS](https://www.raspberrypi.com/software/)
- [DietPi](https://dietpi.com/)
- [Ubuntu for Raspberry Pi](https://ubuntu.com/raspberry-pi)

### 2. Copy project files

```bash
scp -r ./ <user>@<pi-ip>:~/transloc-kiosk/
```

Replace `<user>` with your Pi's username (`pi`, `dietpi`, `ubuntu`, etc.).

### 3. Run setup

```bash
ssh <user>@<pi-ip>
cd ~/transloc-kiosk
sudo bash setup-kiosk.sh
sudo reboot
```

The setup script auto-detects your OS and configures systemd services accordingly.

### 4. Configure buses

Open `http://<pi-ip>:3000/settings` on your phone or laptop and add the buses you want to track.

## Configuration

Buses are stored in `config.json`:

```json
{
  "buses": [
    {
      "agencyId": 85,
      "agencyName": "East Stroudsburg University",
      "agencyLat": 40.99679,
      "agencyLon": -75.16301,
      "routeId": 1003,
      "routeName": "Silver Express",
      "stopId": 1727,
      "stopName": "University Ridge",
      "color": "#4A90D9",
      "description": "Morning commute"
    }
  ]
}
```

## License

MIT
