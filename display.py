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
REFRESH_INTERVAL = 30
WEATHER_INTERVAL = 1800
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

BG = (10, 12, 17)
SURFACE = (21, 24, 32)
SURFACE_HI = (32, 36, 47)
BORDER = (42, 47, 61)
TEXT = (237, 239, 245)
TEXT_DIM = (150, 156, 174)
TEXT_FAINT = (92, 98, 116)
ACCENT = (96, 165, 250)
SUCCESS = (52, 211, 153)
WARNING = (251, 191, 36)
DANGER = (248, 113, 113)
WHITE = (255, 255, 255)
DARK_TEXT = (14, 16, 22)

# Card styles by size. 'normal' is the 2x2 grid card; 'tall' is a half-width,
# full-height card; 'full' is a single card covering the whole card area.
# 'gap' scales the spacing between rows, 'seg' is the (width, height) of one
# load-bar segment, and 'stack_bottom' puts next-bus and load on separate rows.
# Fonts are (size, bold).
CARD_STYLES = {
    'normal': {'pad': 16, 'gap': 1.0, 'radius': 14, 'seg': (12, 6), 'stack_bottom': False,
               'fonts': {'badge': (17, True), 'desc': (14, False), 'text': (14, False),
                         'eta': (56, True), 'unit': (18, False), 'eta_word': (28, True),
                         'small': (12, False)}},
    'tall':   {'pad': 22, 'gap': 1.6, 'radius': 16, 'seg': (16, 8), 'stack_bottom': True,
               'fonts': {'badge': (24, True), 'desc': (17, False), 'text': (17, False),
                         'eta': (96, True), 'unit': (26, False), 'eta_word': (34, True),
                         'small': (14, False)}},
    'full':   {'pad': 32, 'gap': 2.0, 'radius': 18, 'seg': (24, 10), 'stack_bottom': False,
               'fonts': {'badge': (32, True), 'desc': (22, False), 'text': (22, False),
                         'eta': (150, True), 'unit': (36, False), 'eta_word': (56, True),
                         'small': (18, False)}},
}

LOAD_PCT = {'empty': 5, 'low': 25, 'medium': 50, 'half': 50, 'high': 80, 'full': 100}
LOAD_SEGMENTS = 5


def font_candidates():
    """(regular, bold) font files to try, starting with the OS's default UI font."""
    if sys.platform == 'win32':
        fonts = os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts')
        return [(os.path.join(fonts, r), os.path.join(fonts, b)) for r, b in [
            ('segoeui.ttf', 'segoeuib.ttf'),   # Segoe UI
            ('arial.ttf', 'arialbd.ttf'),
        ]]
    if sys.platform == 'darwin':
        # San Francisco ships as a single variable font that pygame can only
        # load in its regular weight, so prefer a family with a real bold file.
        return [
            ('/System/Library/Fonts/Supplemental/Arial.ttf',
             '/System/Library/Fonts/Supplemental/Arial Bold.ttf'),
            ('/System/Library/Fonts/SFNS.ttf', None),
        ]
    t = '/usr/share/fonts/truetype'
    return [
        (f'{t}/piboto/Piboto-Regular.ttf', f'{t}/piboto/Piboto-Bold.ttf'),        # Raspberry Pi OS
        (f'{t}/ubuntu/Ubuntu-R.ttf', f'{t}/ubuntu/Ubuntu-B.ttf'),                 # Ubuntu
        (f'{t}/noto/NotoSans-Regular.ttf', f'{t}/noto/NotoSans-Bold.ttf'),
        (f'{t}/dejavu/DejaVuSans.ttf', f'{t}/dejavu/DejaVuSans-Bold.ttf'),        # DietPi / Debian
        (f'{t}/liberation/LiberationSans-Regular.ttf', f'{t}/liberation/LiberationSans-Bold.ttf'),
    ]


def find_fonts():
    """Return (regular_path, bold_path); either may be None."""
    for regular, bold in font_candidates():
        if os.path.exists(regular):
            return regular, (bold if bold and os.path.exists(bold) else None)
    # Not in a known location: ask the OS font registry (fc-list on Linux)
    names = 'segoeui,sfns,helveticaneue,notosans,dejavusans,liberationsans,arial'
    return pygame.font.match_font(names), pygame.font.match_font(names, bold=True)


def card_layout(count):
    """Return (x, y, w, h, style) slots for the given number of bus cards."""
    top = HEADER_H
    half_w, half_h = WIDTH // 2, CARD_AREA_H // 2
    if count <= 1:
        return [(0, top, WIDTH, CARD_AREA_H, 'full')]
    if count == 2:
        return [(0, top, half_w, CARD_AREA_H, 'tall'),
                (half_w, top, half_w, CARD_AREA_H, 'tall')]
    if count == 3:
        return [(0, top, half_w, CARD_AREA_H, 'tall'),
                (half_w, top, half_w, half_h, 'normal'),
                (half_w, top + half_h, half_w, half_h, 'normal')]
    return [(col * half_w, top + row * half_h, half_w, half_h, 'normal')
            for row in range(2) for col in range(2)]


def fit_text(font, text, max_w):
    """Truncate text with an ellipsis so it renders within max_w pixels."""
    if font.size(text)[0] <= max_w:
        return text
    while text and font.size(text + '...')[0] > max_w:
        text = text[:-1]
    return text.rstrip() + '...'


def ink_height(font, text):
    """Height of the glyphs above the baseline (ignores the font's built-in padding)."""
    return max((m[3] for m in font.metrics(text) if m), default=font.get_ascent())


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


def weather_suggestion(temp_c, precipitation, rain_chance):
    """Warn about rain/snow if it's falling or likely soon, else give the temperature tip."""
    snow = temp_c is not None and temp_c <= 0
    word, tip = ('snow', 'dress warm') if snow else ('rain', 'take an umbrella')
    if precipitation:
        return f'{word.title()}ing now - {tip}'
    if rain_chance is not None and rain_chance >= 50:
        return f'{rain_chance}% chance of {word} - {tip}'
    return temp_suggestion(temp_c)


def arrival_view(bus, now):
    """Pick which upcoming arrivals a card shows at time `now`.

    Returns (target, following, missed): target is the next bus the user can
    still catch given their walk time (any bus if no walk time is set),
    following is the one after it, and missed is the soonest bus when it's
    already too late to walk to it.
    """
    upcoming = [a for a in bus.get('arrivals', []) if a['ts'] > now]
    walk_sec = (bus.get('walk_min') or 0) * 60
    catchable = [a for a in upcoming if a['ts'] - now >= walk_sec]
    target = catchable[0] if catchable else None
    following = catchable[1] if len(catchable) > 1 else None
    missed = upcoming[0] if upcoming and upcoming[0] is not target else None
    return target, following, missed


def hex_to_rgb(hex_str):
    """Convert a hex color string to an RGB tuple."""
    hex_str = hex_str.lstrip('#')
    if len(hex_str) != 6:
        return ACCENT
    try:
        return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))
    except ValueError:
        return ACCENT


def blend(a, b, t):
    """Mix color a toward color b by fraction t."""
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


_shape_cache = {}


def smooth_shape(w, h, radius, fill, border=None, border_w=1, ss=3):
    """Return an anti-aliased rounded rectangle as a cached surface.

    pygame.draw has hard, jagged edges on curves; drawing ss times larger and
    smooth-scaling down gives soft edges. A radius of min(w, h) // 2 makes a
    pill or circle. Results are cached because shapes rarely change.
    """
    key = (w, h, radius, fill, border, border_w)
    surf = _shape_cache.get(key)
    if surf is None:
        if len(_shape_cache) > 200:
            _shape_cache.clear()
        big = pygame.Surface((w * ss, h * ss), pygame.SRCALPHA)
        outer = border or fill
        big.fill((*outer, 0))  # transparent, but same color, so edges don't darken
        pygame.draw.rect(big, outer, big.get_rect(), border_radius=radius * ss)
        if border:
            inner = big.get_rect().inflate(-2 * border_w * ss, -2 * border_w * ss)
            pygame.draw.rect(big, fill, inner, border_radius=max(0, (radius - border_w) * ss))
        surf = pygame.transform.smoothscale(big, (w, h)).convert_alpha()
        _shape_cache[key] = surf
    return surf


def text_on(color):
    """Pick dark or white text for legibility on the given background color."""
    r, g, b = color
    return DARK_TEXT if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else WHITE


def load_percent(load_val):
    """Convert a load value (fraction or label like 'low') to a 0-100 percentage."""
    if load_val is None:
        return None
    if isinstance(load_val, str):
        return LOAD_PCT.get(load_val.lower(), 50)
    return min(100, max(0, int(load_val * 100)))


def load_level(load_val):
    """Convert a load value to (label, color, percent) for display."""
    pct = load_percent(load_val)
    if pct is None:
        return 'No load data', TEXT_FAINT, None
    if isinstance(load_val, str) and load_val.lower() not in LOAD_PCT:
        return load_val.title(), TEXT_DIM, pct
    if pct < 30:
        return 'Low', SUCCESS, pct
    if pct < 70:
        return 'Medium', WARNING, pct
    return 'Full', DANGER, pct


class KioskDisplay:

    def __init__(self):
        pygame.init()

        if sys.platform in ('darwin', 'win32'):
            self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
            pygame.display.set_caption('TransLoc Kiosk')
        elif os.environ.get('DISPLAY'):
            self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN)
            pygame.mouse.set_visible(False)
        else:
            os.environ['SDL_FBDEV'] = '/dev/fb0'
            pygame.display.init()
            self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN)
            pygame.mouse.set_visible(False)

        self.clock = pygame.time.Clock()
        self.running = True

        regular_path, bold_path = find_fonts()
        print(f'Fonts: {regular_path or "pygame default"} / {bold_path or "synthesized bold"}')

        def make_font(size, bold=False):
            path = bold_path if bold and bold_path else regular_path
            try:
                font = pygame.font.Font(path, size)
            except Exception:
                font = pygame.font.Font(None, size)  # pygame's bundled font
            if bold and not (bold_path and path == bold_path):
                font.set_bold(True)
            return font

        self.font_clock = make_font(26, bold=True)
        self.font_temp = make_font(24, bold=True)
        self.font_header = make_font(16)
        self.font_sm = make_font(14)
        self.font_xs = make_font(12)
        self.font_pin = make_font(14, bold=True)
        self.card_fonts = {
            name: {key: make_font(size, bold) for key, (size, bold) in style['fonts'].items()}
            for name, style in CARD_STYLES.items()
        }

        self.config = {'buses': []}
        self.bus_data = []
        self.weather = None
        self.rain_chance = None
        self.pin = None
        self.last_refresh = 0
        self.last_attempt = 0
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

    def fetch_bus(self, bus):
        """Fetch arrivals and vehicle load for one configured bus.

        Sets result['error'] if the data could not be fetched or parsed, so the
        card can show that instead of pretending no buses are running.
        """
        result = {
            'routeName': bus.get('routeName', '?'),
            'stopName': bus.get('stopName', '?'),
            'color': bus.get('color', '#4A90D9'),
            'description': bus.get('description', ''),
            'walk_min': bus.get('walkMin'),
            # Upcoming arrivals as {'ts', 'vehicle', 'load'}; minutes are
            # computed from 'ts' at draw time so the countdown stays live.
            'arrivals': [],
            # Route-wide fallbacks when an arrival's own vehicle is unknown
            'load': None,
            'vehicle_name': None,
            'error': None,
        }

        try:
            arrivals = self.fetch_json(
                f'/api/arrivals?route={bus["routeId"]}&stop={bus["stopId"]}'
            )
            if arrivals is None:
                result['error'] = 'Could not reach TransLoc'
                return result
            future = []
            if arrivals.get('success') and arrivals.get('arrivals'):
                now = time.time()
                # Keep a few extra so the card can move on to later buses
                # between refreshes (or skip ones too soon to walk to).
                future = sorted(
                    [a for a in arrivals['arrivals'] if a.get('timestamp', 0) > now],
                    key=lambda a: a['timestamp']
                )[:4]

            vehicles = self.fetch_json(
                f'/api/vehicles?agency={bus["agencyId"]}&route={bus["routeId"]}'
            )
            if vehicles is None:
                result['error'] = 'Could not reach TransLoc'
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

            for a in future:
                vehicle = a.get('call_name')
                result['arrivals'].append({
                    'ts': a['timestamp'],
                    'vehicle': vehicle,
                    'load': vehicle_loads.get(vehicle) if vehicle else None,
                })
        except Exception as e:
            # Unexpected response shape (e.g. TransLoc changed their API)
            print(f'Bad data for route {bus.get("routeId")}: {e}')
            result['error'] = 'Unexpected data from TransLoc'
        return result

    def refresh_data(self):
        """Fetch all data from the backend sequentially to reduce Pi load."""
        if not self._refresh_lock.acquire(blocking=False):
            return

        def _fetch():
            try:
                cfg = self.fetch_json('/api/config')
                if cfg is None:
                    self.error_msg = 'Kiosk server unreachable'
                    # Old ETAs would be stale, so drop them
                    self.bus_data = [dict(b, arrivals=[], error=self.error_msg)
                                     for b in self.bus_data]
                    return
                if 'buses' in cfg:
                    self.config = cfg

                pin = self.fetch_json('/api/pin')
                if pin and 'pin' in pin:
                    self.pin = pin['pin']

                bus_results = []
                for i, bus in enumerate(self.config.get('buses', [])[:4]):
                    bus_results.append(self.fetch_bus(bus))
                    if i < 3:
                        time.sleep(0.5)

                self.bus_data = bus_results

                now = time.time()
                weather_interval = WEATHER_INTERVAL if self.weather else 30
                if now - self.last_weather_refresh > weather_interval:
                    buses = self.config.get('buses', [])
                    if buses:
                        lat = buses[0].get('agencyLat')
                        lon = buses[0].get('agencyLon')
                        if lat and lon:
                            w = self.fetch_json(f'/api/weather?lat={lat}&lon={lon}')
                            if w and 'current' in w:
                                self.weather = w['current']
                                chances = (w.get('hourly') or {}).get('precipitation_probability') or []
                                chances = [c for c in chances if c is not None]
                                self.rain_chance = max(chances) if chances else None
                                self.last_weather_refresh = now

                errors = [b['error'] for b in bus_results if b['error']]
                if errors:
                    self.error_msg = errors[0]
                else:
                    self.last_refresh = time.time()
                    self.last_update_text = 'Just now'
                    self.error_msg = None

            except Exception as e:
                self.error_msg = str(e)
                print(f'Refresh error: {e}')
            finally:
                # Schedule the next attempt even after a failure, so a broken
                # network doesn't cause a retry on every frame.
                self.last_attempt = time.time()
                self._refresh_lock.release()

        thread = threading.Thread(target=_fetch, daemon=True)
        thread.start()

    def draw_header(self):
        mid = HEADER_H // 2 + 2

        # Clock with the date beside it, sharing a baseline
        clock_surf = self.font_clock.render(time.strftime('%H:%M'), True, TEXT)
        clock_y = mid - clock_surf.get_height() // 2
        self.screen.blit(clock_surf, (20, clock_y))
        t = time.localtime()
        date_text = f'{time.strftime("%a", t)}, {time.strftime("%b", t)} {t.tm_mday}'
        date_surf = self.font_header.render(date_text, True, TEXT_DIM)
        baseline = clock_y + self.font_clock.get_ascent()
        self.screen.blit(date_surf, (20 + clock_surf.get_width() + 12,
                                     baseline - self.font_header.get_ascent()))

        # Weather on the right: suggestion | temperature
        right = WIDTH - 20
        if self.weather:
            temp = self.weather.get('temperature_2m')
            temp_str = f'{temp:.0f}\u00b0C' if temp is not None else '--\u00b0C'
            temp_surf = self.font_temp.render(temp_str, True, TEXT)
            temp_x = right - temp_surf.get_width()
            self.screen.blit(temp_surf, (temp_x, mid - temp_surf.get_height() // 2))

            pygame.draw.line(self.screen, BORDER, (temp_x - 14, mid - 10), (temp_x - 14, mid + 10))

            suggestion = weather_suggestion(temp, self.weather.get('precipitation'), self.rain_chance)
            sug_surf = self.font_header.render(suggestion, True, TEXT_DIM)
            self.screen.blit(sug_surf, (temp_x - 28 - sug_surf.get_width(),
                                        mid - sug_surf.get_height() // 2))
        else:
            no_weather = self.font_header.render('Weather loading...', True, TEXT_FAINT)
            self.screen.blit(no_weather, (right - no_weather.get_width(),
                                          mid - no_weather.get_height() // 2))

    def blit_shape(self, x, y, w, h, radius, fill, border=None, border_w=1):
        self.screen.blit(smooth_shape(w, h, radius, fill, border, border_w), (x, y))

    def load_widget_width(self, font, style, label):
        seg_w, _ = style['seg']
        seg_gap = max(3, seg_w // 4)
        return LOAD_SEGMENTS * seg_w + (LOAD_SEGMENTS - 1) * seg_gap + 10 + font.size(label)[0]

    def draw_load_widget(self, x, center_y, font, style, load_val):
        """Draw a segmented occupancy bar followed by its label."""
        label, color, pct = load_level(load_val)
        seg_w, seg_h = style['seg']
        seg_gap = max(3, seg_w // 4)
        lit = 0 if pct is None else max(1, math.ceil(pct / (100 / LOAD_SEGMENTS)))
        off_color = blend(SURFACE, TEXT_FAINT, 0.45)
        for i in range(LOAD_SEGMENTS):
            self.blit_shape(x + i * (seg_w + seg_gap), center_y - seg_h // 2, seg_w, seg_h,
                            seg_h // 2, color if i < lit else off_color)
        label_surf = font.render(label, True, color)
        label_x = x + LOAD_SEGMENTS * (seg_w + seg_gap) - seg_gap + 10
        self.screen.blit(label_surf, (label_x, center_y - label_surf.get_height() // 2))

    def draw_bus_card(self, slot, bus):
        x, y, w, h, style_name = slot
        style = CARD_STYLES[style_name]
        fonts = self.card_fonts[style_name]
        pad, gap = style['pad'], style['gap']

        def sp(px):
            return int(px * gap)

        color = hex_to_rgb(bus.get('color', '#4A90D9'))
        card_bg = blend(SURFACE, color, 0.07)
        self.blit_shape(x + 4, y + 4, w - 8, h - 8, style['radius'], card_bg,
                        blend(BORDER, color, 0.35))

        left = x + 4 + pad
        right = x + w - 4 - pad
        content_w = right - left
        text_font = fonts['text']
        text_h = text_font.get_height()

        now = time.time()
        target, following, missed = arrival_view(bus, now)
        walk = bus.get('walk_min') or 0

        def mins(arrival):
            return max(0, int((arrival['ts'] - now) // 60))

        blink_on = (now % 0.8) < 0.4
        go_color = SUCCESS if blink_on else blend(SUCCESS, BG, 0.5)

        # ETA block: a big number with a small unit, or a status word.
        # With a walk time set, the number is when to leave, not when the bus comes.
        eta_font, unit_text = fonts['eta'], ''
        if target and walk:
            leave = max(0, int((target['ts'] - now - walk * 60) // 60))
            if leave == 0:
                eta_text, unit_text, eta_color = 'Go', 'leave now', go_color
            else:
                eta_text, unit_text = str(leave), 'min to leave'
                eta_color = WARNING if leave <= 3 else TEXT
        elif target:
            eta = mins(target)
            if eta == 0:
                eta_text, unit_text, eta_color = 'Now', 'arriving', go_color
            else:
                eta_text, unit_text = str(eta), 'min'
                if eta <= 5:
                    eta_color = SUCCESS
                elif eta <= 15:
                    eta_color = WARNING
                else:
                    eta_color = TEXT
        else:
            eta_font = fonts['eta_word']
            if missed:
                eta_text, eta_color = 'Too late', WARNING
            elif bus.get('error'):
                eta_text, eta_color = 'No data', DANGER
            else:
                eta_text, eta_color = 'No buses running', TEXT_DIM
        eta_text = fit_text(eta_font, eta_text, content_w)
        eta_ink = ink_height(eta_font, eta_text)

        # Bottom line text
        if target and walk:
            next_text = f'Bus in {mins(target)} min'
            if following:
                next_text += f' · next {mins(following)} min'
        elif target:
            if following:
                next_text = f'Next in {mins(following)} min'
                next_pct = load_percent(following['load'])
                if next_pct is not None:
                    next_text += f' · {next_pct}% full'
            else:
                next_text = 'No next bus today'
        elif missed:
            next_text = f'Bus in {mins(missed)} min · {walk} min walk'
        else:
            next_text = ''

        # Load and vehicle for the bus being shown. The route-wide fallbacks
        # only apply to the soonest bus, matching how they were fetched.
        shown = target or missed
        if shown:
            is_soonest = not (target and missed)
            load_val = shown['load']
            if load_val is None and is_soonest:
                load_val = bus.get('load')
            vname = shown['vehicle'] or (bus.get('vehicle_name') if is_soonest else None)
        else:
            load_val, vname = bus.get('load'), bus.get('vehicle_name')

        badge_font = fonts['badge']
        badge_h = badge_font.get_height() + 2 * sp(4)
        stack = style['stack_bottom']
        bottom_h = text_h * 2 + sp(8) if stack else text_h

        total_h = badge_h + sp(12) + text_h + sp(14) + eta_ink + sp(16) + bottom_h
        cy = y + 4 + max(pad, (h - 8 - total_h) // 2)

        # Top row: route badge, description, vehicle number
        vn_surf = None
        if vname:
            small = fonts['small']
            vn_surf = small.render(fit_text(small, f'Bus {vname}', content_w // 3), True, TEXT_FAINT)
            self.screen.blit(vn_surf, (right - vn_surf.get_width(),
                                       cy + (badge_h - vn_surf.get_height()) // 2))

        badge_text = fit_text(badge_font, bus.get('routeName', 'Unknown'),
                              int(content_w * 0.65) - 2 * sp(12))
        badge_surf = badge_font.render(badge_text, True, text_on(color))
        badge_w = badge_surf.get_width() + 2 * sp(12)
        self.blit_shape(left, cy, badge_w, badge_h, badge_h // 2, color)
        self.screen.blit(badge_surf, (left + sp(12), cy + (badge_h - badge_surf.get_height()) // 2))

        desc = bus.get('description', '')
        desc_x = left + badge_w + sp(10)
        desc_w = (right - (vn_surf.get_width() + sp(10) if vn_surf else 0)) - desc_x
        if desc and desc_w > 30:
            desc_font = fonts['desc']
            desc_surf = desc_font.render(fit_text(desc_font, desc, desc_w), True,
                                         blend(color, TEXT, 0.5))
            self.screen.blit(desc_surf, (desc_x, cy + (badge_h - desc_surf.get_height()) // 2))
        cy += badge_h + sp(12)

        # Stop row: hollow stop marker + name
        marker_d = 2 * max(3, text_h // 4)
        self.blit_shape(left, cy + (text_h - marker_d) // 2, marker_d, marker_d, marker_d // 2,
                        card_bg, color, border_w=2)
        stop_x = left + marker_d + sp(8)
        stop_surf = text_font.render(fit_text(text_font, bus.get('stopName', '?'), right - stop_x),
                                     True, TEXT_DIM)
        self.screen.blit(stop_surf, (stop_x, cy))
        cy += text_h + sp(14)

        # ETA row, aligned on the glyphs' baseline
        baseline = cy + eta_ink
        eta_surf = eta_font.render(eta_text, True, eta_color)
        self.screen.blit(eta_surf, (left, baseline - eta_font.get_ascent()))
        if unit_text:
            unit_font = fonts['unit']
            unit_surf = unit_font.render(unit_text, True, TEXT_DIM)
            self.screen.blit(unit_surf, (left + eta_surf.get_width() + sp(8),
                                         baseline - unit_font.get_ascent()))
        cy = baseline + sp(16)

        # Bottom: next bus + occupancy
        load_label = load_level(load_val)[0]
        load_w = self.load_widget_width(text_font, style, load_label)
        if stack:
            next_max = content_w
            load_x, load_y = left, cy + text_h + sp(8) + text_h // 2
        else:
            next_max = content_w - load_w - sp(16)
            load_x, load_y = right - load_w, cy + text_h // 2
        if next_text:
            next_surf = text_font.render(fit_text(text_font, next_text, next_max), True, TEXT_DIM)
            self.screen.blit(next_surf, (left, cy))
        self.draw_load_widget(load_x, load_y, text_font, style, load_val)

    def draw_empty_card(self, slot):
        x, y, w, h, style_name = slot
        fonts = self.card_fonts[style_name]

        self.blit_shape(x + 4, y + 4, w - 8, h - 8, CARD_STYLES[style_name]['radius'],
                        SURFACE, BORDER)

        if not self.last_attempt:
            msg_text, sub_text, msg_color = 'Loading...', '', TEXT_DIM
        elif self.error_msg:
            msg_text, sub_text, msg_color = 'No data', self.error_msg, DANGER
        else:
            msg_text, sub_text, msg_color = ('No buses configured',
                                             f'Add one at http://{_cached_lan_ip}:3000/settings',
                                             TEXT)
        msg = fonts['eta_word'].render(msg_text, True, msg_color)
        sub = fonts['text'].render(sub_text, True, TEXT_DIM)
        self.screen.blit(msg, (x + w // 2 - msg.get_width() // 2,
                               y + h // 2 - msg.get_height()))
        self.screen.blit(sub, (x + w // 2 - sub.get_width() // 2,
                               y + h // 2 + 12))

    def draw_footer(self):
        y = HEIGHT - FOOTER_H
        mid = y + FOOTER_H // 2 - 2
        pygame.draw.line(self.screen, BORDER, (20, y), (WIDTH - 20, y))

        btn_text = self.font_sm.render('Refresh', True, TEXT)
        btn_w = btn_text.get_width() + 32
        btn_h = 26
        self.refresh_btn_rect = pygame.Rect(20, mid - btn_h // 2, btn_w, btn_h)
        self.blit_shape(*self.refresh_btn_rect, btn_h // 2, SURFACE_HI, BORDER)
        self.screen.blit(btn_text, (self.refresh_btn_rect.x + (btn_w - btn_text.get_width()) // 2,
                                    mid - btn_text.get_height() // 2))

        elapsed = int(time.time() - self.last_refresh)
        if not self.last_refresh:
            update_str = 'Not updated yet'
        elif elapsed < 5:
            update_str = 'Updated just now'
        elif elapsed < 60:
            update_str = f'Updated {elapsed}s ago'
        else:
            update_str = f'Updated {elapsed // 60}m ago'

        if self.error_msg:
            status, dot_color = f'{self.error_msg} · {update_str}', DANGER
        elif self.last_refresh and elapsed > 3 * REFRESH_INTERVAL:
            status, dot_color = update_str, WARNING
        elif self.last_refresh:
            status, dot_color = f'Live · {update_str}', SUCCESS
        else:
            status, dot_color = update_str, TEXT_FAINT

        # Right side, laid out right to left: settings URL, then the PIN
        # needed to save changes there
        x = WIDTH - 20
        if self.pin:
            pin_surf = self.font_pin.render(self.pin, True, TEXT)
            x -= pin_surf.get_width()
            self.screen.blit(pin_surf, (x, mid - pin_surf.get_height() // 2))
            pin_label = self.font_xs.render('PIN', True, TEXT_FAINT)
            x -= 6 + pin_label.get_width()
            self.screen.blit(pin_label, (x, mid - pin_label.get_height() // 2))
            x -= 16
        url_surf = self.font_xs.render(f'{_cached_lan_ip}:3000/settings', True, ACCENT)
        x -= url_surf.get_width()
        self.screen.blit(url_surf, (x, mid - url_surf.get_height() // 2))
        url_label = self.font_xs.render('Settings', True, TEXT_FAINT)
        x -= 8 + url_label.get_width()
        self.screen.blit(url_label, (x, mid - url_label.get_height() // 2))

        dot_x = self.refresh_btn_rect.right + 16
        self.blit_shape(dot_x, mid - 4, 8, 8, 4, dot_color)
        status_x = dot_x + 16
        status_surf = self.font_xs.render(
            fit_text(self.font_xs, status, x - 24 - status_x), True, TEXT_DIM)
        self.screen.blit(status_surf, (status_x, mid - status_surf.get_height() // 2))

    def draw(self):
        self.screen.fill(BG)
        self.draw_header()

        slots = card_layout(len(self.bus_data))
        if self.bus_data:
            for slot, bus in zip(slots, self.bus_data):
                self.draw_bus_card(slot, bus)
        else:
            self.draw_empty_card(slots[0])

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
            if now - self.last_attempt >= REFRESH_INTERVAL:
                self.refresh_data()

            self.draw()
            self.clock.tick(15)

        pygame.quit()


def main():
    app = KioskDisplay()
    app.run()


if __name__ == '__main__':
    main()
