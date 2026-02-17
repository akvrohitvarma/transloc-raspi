#!/usr/bin/env python3
"""
TransLoc Bus Tracker Kiosk Display

Pygame-based 800x480 dashboard for Raspberry Pi 2.
Fetches transit and weather data from the local Flask server
and renders a real-time kiosk interface.
"""

import pygame
import requests
import time
import math
import threading
import os
import sys
import socket

WIDTH, HEIGHT = 800, 480
HEADER_H = 48
FOOTER_H = 40
CARD_AREA_H = HEIGHT - HEADER_H - FOOTER_H
CARD_W = WIDTH // 2
CARD_H = CARD_AREA_H // 2
REFRESH_INTERVAL = 30
WEATHER_INTERVAL = 3600
SERVER_URL = os.environ.get('KIOSK_SERVER', 'http://localhost:3000')


def get_local_ip():
    """Resolve the device's LAN IP address via a UDP socket probe."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return 'localhost'


_cached_lan_ip = get_local_ip()

BG = (15, 17, 23)
SURFACE = (26, 29, 39)
BORDER = (46, 51, 69)
TEXT = (228, 230, 240)
TEXT_DIM = (139, 143, 163)
ACCENT = (74, 144, 217)
SUCCESS = (45, 212, 168)
DANGER = (231, 76, 95)
WHITE = (255, 255, 255)
HEADER_TEXT = (190, 193, 200)


def temp_suggestion(temp_c):
    """Return a short clothing/gear suggestion for the given temperature."""
    if temp_c is None:
        return 'Enjoy your day!'
    if temp_c <= 0:
        return 'Wear Heavy coat & gloves!'
    elif temp_c <= 10:
        return 'Wear a warm jacket!'
    elif temp_c <= 18:
        return 'Wear Light layers today'
    elif temp_c <= 28:
        return 'Enjoy your day!'
    elif temp_c <= 35:
        return 'Put on sunscreen & shades!'
    else:
        return 'Stay hydrated!'


def hex_to_rgb(hex_str):
    """Convert a hex color string to an RGB tuple."""
    hex_str = hex_str.lstrip('#')
    if len(hex_str) != 6:
        return ACCENT
    try:
        return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))
    except ValueError:
        return ACCENT


def darken(color, factor=0.3):
    return tuple(max(0, int(c * factor)) for c in color)


def load_indicator_text(load_val):
    """Convert a load value to (label, color, fill_fraction) for display."""
    if load_val is None:
        return 'N/A', TEXT_DIM, 0
    if isinstance(load_val, str):
        lv = load_val.lower()
        pct_map = {'empty': 5, 'low': 25, 'medium': 50, 'half': 50, 'high': 80, 'full': 100}
        pct = pct_map.get(lv, 50)
        if lv in ('empty', 'low'):
            return f'Low ({pct}%)', SUCCESS, pct / 100
        elif lv in ('medium', 'half'):
            return f'Medium ({pct}%)', (255, 193, 7), pct / 100
        elif lv in ('high', 'full'):
            return f'Full ({pct}%)', DANGER, pct / 100
        return f'{load_val.title()} ({pct}%)', TEXT_DIM, pct / 100
    pct = min(100, max(0, int(load_val * 100)))
    fill = min(1.0, max(0.0, float(load_val)))
    if pct < 30:
        return f'Low ({pct}%)', SUCCESS, fill
    elif pct < 70:
        return f'Medium ({pct}%)', (255, 193, 7), fill
    else:
        return f'Full ({pct}%)', DANGER, fill


class KioskDisplay:

    def __init__(self):
        pygame.init()

        if os.environ.get('DISPLAY') or sys.platform == 'darwin':
            self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
            pygame.display.set_caption('TransLoc Kiosk')
        else:
            os.environ['SDL_FBDEV'] = '/dev/fb0'
            pygame.display.init()
            self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN)
            pygame.mouse.set_visible(False)

        self.clock = pygame.time.Clock()
        self.running = True

        try:
            font_path = None
            for fp in [
                '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
                '/System/Library/Fonts/Helvetica.ttc',
                '/System/Library/Fonts/SFNSText.ttf',
            ]:
                if os.path.exists(fp):
                    font_path = fp
                    break

            if font_path:
                self.font_lg = pygame.font.Font(font_path, 22)
                self.font_lg_bold = pygame.font.Font(font_path, 24)
                self.font_md = pygame.font.Font(font_path, 24)
                self.font_sm = pygame.font.Font(font_path, 14)
                self.font_sm_bold = pygame.font.Font(font_path, 24)
                self.font_xs = pygame.font.Font(font_path, 12)
                self.font_xl = pygame.font.Font(font_path, 42)
                self.font_route = pygame.font.Font(font_path, 36)
            else:
                self.font_lg = pygame.font.SysFont('sans-serif', 22)
                self.font_lg_bold = pygame.font.SysFont('sans-serif', 22, bold=True)
                self.font_md = pygame.font.SysFont('sans-serif', 17)
                self.font_sm = pygame.font.SysFont('sans-serif', 14)
                self.font_sm_bold = pygame.font.SysFont('sans-serif', 14, bold=True)
                self.font_xs = pygame.font.SysFont('sans-serif', 12)
                self.font_xl = pygame.font.SysFont('sans-serif', 42)
                self.font_route = pygame.font.SysFont('sans-serif', 36, bold=True)
        except Exception:
            self.font_lg = pygame.font.SysFont(None, 24)
            self.font_lg_bold = pygame.font.SysFont(None, 24, bold=True)
            self.font_md = pygame.font.SysFont(None, 18)
            self.font_sm = pygame.font.SysFont(None, 15)
            self.font_sm_bold = pygame.font.SysFont(None, 15, bold=True)
            self.font_xs = pygame.font.SysFont(None, 13)
            self.font_xl = pygame.font.SysFont(None, 38)
            self.font_route = pygame.font.SysFont(None, 28, bold=True)

        self.config = {'buses': []}
        self.bus_data = []
        self.weather = None
        self.last_refresh = 0
        self.last_weather_refresh = 0
        self.last_update_text = 'Never'
        self.error_msg = None
        self._seen_errors = set()
        self._refresh_lock = threading.Lock()

        self.refresh_data()

    def fetch_json(self, url):
        """Fetch JSON from the local server with error deduplication."""
        try:
            r = requests.get(f'{SERVER_URL}{url}', timeout=12)
            r.raise_for_status()
            self._seen_errors.discard(url)
            return r.json()
        except Exception as e:
            if url not in self._seen_errors:
                print(f'Fetch error {url}: {e}')
                self._seen_errors.add(url)
                if len(self._seen_errors) > 50:
                    self._seen_errors.clear()
            return None

    def refresh_data(self):
        """Fetch all data from the backend sequentially to reduce Pi load."""
        if not self._refresh_lock.acquire(blocking=False):
            return

        def _fetch():
            try:
                cfg = self.fetch_json('/api/config')
                if cfg and 'buses' in cfg:
                    self.config = cfg

                bus_results = []
                for i, bus in enumerate(self.config.get('buses', [])[:4]):
                    result = {
                        'routeName': bus.get('routeName', '?'),
                        'stopName': bus.get('stopName', '?'),
                        'color': bus.get('color', '#4A90D9'),
                        'description': bus.get('description', ''),
                        'eta_min': None,
                        'next_eta_min': None,
                        'next_load': None,
                        'load': None,
                        'vehicle_name': None,
                        'error': None,
                    }

                    arrivals = self.fetch_json(
                        f'/api/arrivals?route={bus["routeId"]}&stop={bus["stopId"]}'
                    )
                    if arrivals and arrivals.get('success') and arrivals.get('arrivals'):
                        now = time.time()
                        future = sorted(
                            [a for a in arrivals['arrivals'] if a.get('timestamp', 0) > now],
                            key=lambda a: a['timestamp']
                        )[:2]
                        if future:
                            eta_sec = future[0]['timestamp'] - now
                            result['eta_min'] = max(0, int(eta_sec / 60))
                            result['vehicle_name'] = future[0].get('call_name')
                        if len(future) > 1:
                            next_sec = future[1]['timestamp'] - now
                            result['next_eta_min'] = max(0, int(next_sec / 60))
                            result['_next_call_name'] = future[1].get('call_name')

                    vehicles = self.fetch_json(
                        f'/api/vehicles?agency={bus["agencyId"]}&route={bus["routeId"]}'
                    )
                    vehicle_loads = {}
                    if vehicles and vehicles.get('success') and vehicles.get('vehicles'):
                        for v in vehicles['vehicles']:
                            if v.get('route_id') == bus['routeId']:
                                cn = v.get('call_name')
                                if cn:
                                    vehicle_loads[cn] = v.get('load')
                                if result['load'] is None:
                                    result['load'] = v.get('load')
                                if not result['vehicle_name']:
                                    result['vehicle_name'] = v.get('call_name')

                    if result.get('vehicle_name') and result['vehicle_name'] in vehicle_loads:
                        result['load'] = vehicle_loads[result['vehicle_name']]
                    if result.get('_next_call_name') and result['_next_call_name'] in vehicle_loads:
                        result['next_load'] = vehicle_loads[result['_next_call_name']]
                    result.pop('_next_call_name', None)

                    bus_results.append(result)

                    if i < 3:
                        time.sleep(0.5)

                self.bus_data = bus_results

                now = time.time()
                if now - self.last_weather_refresh > WEATHER_INTERVAL:
                    buses = self.config.get('buses', [])
                    if buses:
                        lat = buses[0].get('agencyLat')
                        lon = buses[0].get('agencyLon')
                        if lat and lon:
                            w = self.fetch_json(f'/api/weather?lat={lat}&lon={lon}')
                            if w and 'current' in w:
                                self.weather = w['current']
                    self.last_weather_refresh = now

                self.last_refresh = time.time()
                self.last_update_text = 'Just now'
                self.error_msg = None

            except Exception as e:
                self.error_msg = str(e)
                print(f'Refresh error: {e}')
            finally:
                self._refresh_lock.release()

        thread = threading.Thread(target=_fetch, daemon=True)
        thread.start()

    def draw_header(self):
        rect = pygame.Rect(0, 0, WIDTH, HEADER_H)
        pygame.draw.rect(self.screen, SURFACE, rect)
        pygame.draw.line(self.screen, BORDER, (0, HEADER_H - 1), (WIDTH, HEADER_H - 1))

        clock_text = time.strftime('%H:%M')
        clock_surf = self.font_lg_bold.render(clock_text, True, HEADER_TEXT)
        self.screen.blit(clock_surf, (16, (HEADER_H - clock_surf.get_height()) // 2))

        if self.weather:
            temp_raw = self.weather.get('temperature_2m')
            temp = (temp_raw + 2) if temp_raw is not None else None
            temp_str = f'{temp:.0f}\u00b0C' if temp is not None else '--\u00b0C'
            weather_surf = self.font_md.render(temp_str, True, HEADER_TEXT)
            self.screen.blit(weather_surf, (WIDTH // 2 - weather_surf.get_width() // 2,
                                            (HEADER_H - weather_surf.get_height()) // 2))

            suggestion = temp_suggestion(temp)
            sug_surf = self.font_sm_bold.render(suggestion, True, HEADER_TEXT)
            self.screen.blit(sug_surf, (WIDTH - sug_surf.get_width() - 16,
                                         (HEADER_H - sug_surf.get_height()) // 2))
        else:
            no_weather = self.font_sm.render('Weather loading...', True, TEXT_DIM)
            self.screen.blit(no_weather, (WIDTH // 2 - no_weather.get_width() // 2,
                                          (HEADER_H - no_weather.get_height()) // 2))

    def draw_bus_card(self, index, bus):
        col = index % 2
        row = index // 2
        x = col * CARD_W
        y = HEADER_H + row * CARD_H

        color = hex_to_rgb(bus.get('color', '#4A90D9'))
        bg_color = darken(color, 0.15)
        border_color = darken(color, 0.5)

        card_rect = pygame.Rect(x + 4, y + 4, CARD_W - 8, CARD_H - 8)
        pygame.draw.rect(self.screen, bg_color, card_rect, border_radius=10)
        pygame.draw.rect(self.screen, border_color, card_rect, width=2, border_radius=10)

        accent_rect = pygame.Rect(x + 4, y + 4, 6, CARD_H - 8)
        pygame.draw.rect(self.screen, color, accent_rect,
                         border_top_left_radius=10, border_bottom_left_radius=10)

        cx = x + 20
        cy = y + 16

        eta_min = bus.get('eta_min')
        route_name = bus.get('routeName', 'Unknown')
        name_surf = self.font_route.render(route_name, True, TEXT)
        self.screen.blit(name_surf, (cx, cy))
        cy += name_surf.get_height() + 4

        desc = bus.get('description', '')
        if desc:
            desc_surf = self.font_xs.render(desc, True, color)
            self.screen.blit(desc_surf, (cx, cy))
            cy += desc_surf.get_height() + 4

        stop_name = bus.get('stopName', '?')
        if len(stop_name) > 35:
            stop_name = stop_name[:32] + '...'
        stop_surf = self.font_sm.render(f'Stop: {stop_name}', True, TEXT_DIM)
        self.screen.blit(stop_surf, (cx, cy))
        cy += stop_surf.get_height() + 10

        if eta_min is not None:
            if eta_min == 0:
                eta_text = 'Arriving NOW!'
                blink_on = (time.time() % 0.8) < 0.4
                eta_color = SUCCESS if blink_on else (20, 100, 80)
            elif eta_min <= 5:
                eta_text = f'{eta_min} minute{"s" if eta_min > 1 else ""}'
                eta_color = SUCCESS
            elif eta_min <= 15:
                eta_text = f'{eta_min} minutes'
                eta_color = (255, 193, 7)
            else:
                eta_text = f'{eta_min} minutes'
                eta_color = TEXT
            eta_surf = self.font_xl.render(eta_text, True, eta_color)
        else:
            eta_surf = self.font_xl.render('No active buses', True, TEXT_DIM)
        self.screen.blit(eta_surf, (cx, cy))
        cy += eta_surf.get_height() + 2

        next_eta = bus.get('next_eta_min')
        if next_eta is not None:
            next_load = bus.get('next_load')
            if next_load is not None:
                load_pct = min(100, max(0, int(next_load * 100))) if isinstance(next_load, (int, float)) else 0
                next_text = f'Next bus is in: {next_eta} min, with {load_pct}% load'
            else:
                next_text = f'Next bus is in: {next_eta} min'
            next_surf = self.font_sm.render(next_text, True, TEXT_DIM)
            self.screen.blit(next_surf, (cx, cy))
            cy += next_surf.get_height() + 6
        elif eta_min is not None:
            next_surf = self.font_sm.render('No next bus today', True, TEXT_DIM)
            self.screen.blit(next_surf, (cx, cy))
            cy += next_surf.get_height() + 6
        else:
            cy += 8

        load_text, load_color, fill_pct = load_indicator_text(bus.get('load'))
        load_label = self.font_sm.render(f'Load: {load_text}', True, load_color)
        self.screen.blit(load_label, (cx, cy))

        bar_x = cx + load_label.get_width() + 10
        bar_y = cy + 2
        bar_w = 100
        bar_h = 12
        pygame.draw.rect(self.screen, darken(color, 0.3),
                         (bar_x, bar_y, bar_w, bar_h), border_radius=4)

        if fill_pct > 0:
            fill_w = max(4, int(bar_w * fill_pct))
            pygame.draw.rect(self.screen, load_color,
                             (bar_x, bar_y, fill_w, bar_h), border_radius=4)

        vname = bus.get('vehicle_name')
        if vname:
            if len(vname) > 25:
                vname = vname[:22] + '...'
            vn_surf = self.font_xs.render(f'Bus: {vname}', True, TEXT_DIM)
            self.screen.blit(vn_surf, (x + CARD_W - vn_surf.get_width() - 16,
                                       y + CARD_H - 24))

    def draw_empty_card(self, index):
        col = index % 2
        row = index // 2
        x = col * CARD_W
        y = HEADER_H + row * CARD_H

        card_rect = pygame.Rect(x + 4, y + 4, CARD_W - 8, CARD_H - 8)
        pygame.draw.rect(self.screen, SURFACE, card_rect, border_radius=10)
        pygame.draw.rect(self.screen, BORDER, card_rect, width=1, border_radius=10)

        msg = self.font_md.render('No bus configured', True, TEXT_DIM)
        sub = self.font_xs.render('Use settings page to add', True, TEXT_DIM)
        self.screen.blit(msg, (x + CARD_W // 2 - msg.get_width() // 2,
                               y + CARD_H // 2 - 16))
        self.screen.blit(sub, (x + CARD_W // 2 - sub.get_width() // 2,
                               y + CARD_H // 2 + 10))

    def draw_footer(self):
        y = HEIGHT - FOOTER_H
        rect = pygame.Rect(0, y, WIDTH, FOOTER_H)
        pygame.draw.rect(self.screen, SURFACE, rect)
        pygame.draw.line(self.screen, BORDER, (0, y), (WIDTH, y))

        btn_text = self.font_sm.render('Refresh', True, WHITE)
        btn_w = btn_text.get_width() + 28
        btn_h = 28
        btn_x = 12
        btn_y = y + (FOOTER_H - btn_h) // 2
        self.refresh_btn_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)

        pygame.draw.rect(self.screen, ACCENT, self.refresh_btn_rect, border_radius=6)
        highlight_rect = pygame.Rect(btn_x + 1, btn_y + 1, btn_w - 2, btn_h // 2)
        highlight_surf = pygame.Surface((highlight_rect.w, highlight_rect.h), pygame.SRCALPHA)
        highlight_surf.fill((255, 255, 255, 25))
        self.screen.blit(highlight_surf, highlight_rect.topleft)
        self.screen.blit(btn_text, (btn_x + (btn_w - btn_text.get_width()) // 2,
                                     btn_y + (btn_h - btn_text.get_height()) // 2))

        elapsed = int(time.time() - self.last_refresh) if self.last_refresh else 0
        if elapsed < 5:
            update_str = 'Updated just now'
        elif elapsed < 60:
            update_str = f'Updated {elapsed}s ago'
        else:
            update_str = f'Updated {elapsed // 60}m ago'
        upd_surf = self.font_xs.render(update_str, True, TEXT_DIM)
        self.screen.blit(upd_surf, (WIDTH // 2 - upd_surf.get_width() // 2,
                                     y + (FOOTER_H - upd_surf.get_height()) // 2))

        settings_url = f'http://{_cached_lan_ip}:3000/settings'
        settings_surf = self.font_xs.render(settings_url, True, ACCENT)
        self.screen.blit(settings_surf, (WIDTH - settings_surf.get_width() - 12,
                                          y + (FOOTER_H - settings_surf.get_height()) // 2))

        if self.error_msg:
            err_surf = self.font_xs.render(f'Error: {self.error_msg[:40]}', True, DANGER)
            self.screen.blit(err_surf, (WIDTH // 2 - err_surf.get_width() // 2, y + 2))

    def draw(self):
        self.screen.fill(BG)
        self.draw_header()

        for i in range(4):
            if i < len(self.bus_data):
                self.draw_bus_card(i, self.bus_data[i])
            else:
                self.draw_empty_card(i)

        self.draw_footer()
        pygame.display.flip()

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE or event.key == pygame.K_q:
                    self.running = False
                elif event.key == pygame.K_r:
                    self.refresh_data()
                elif event.key == pygame.K_s:
                    print(f'Settings page: {SERVER_URL}/settings')
            elif event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                if hasattr(self, 'refresh_btn_rect') and self.refresh_btn_rect.collidepoint(mx, my):
                    self.refresh_data()

    def run(self):
        print(f'TransLoc Kiosk Display started ({WIDTH}x{HEIGHT})')
        print(f'Server: {SERVER_URL}')
        print(f'Press R to refresh, Q/Esc to quit')
        print(f'Configure buses at: http://{_cached_lan_ip}:3000/settings')

        while self.running:
            self.handle_events()

            now = time.time()
            if now - self.last_refresh >= REFRESH_INTERVAL:
                self.refresh_data()

            self.draw()
            self.clock.tick(15)

        pygame.quit()


def main():
    app = KioskDisplay()
    app.run()


if __name__ == '__main__':
    main()
