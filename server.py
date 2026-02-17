#!/usr/bin/env python3
"""
TransLoc Kiosk Server

Flask backend that proxies TransLoc and Open-Meteo APIs,
manages kiosk configuration, and serves the settings page.
"""

import json
import os
import time
import requests
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder='public', static_url_path='')
PORT = 3000
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
TRANSLOC_BASE = 'https://hermes.transloc.com/v1'
WEATHER_BASE = 'https://api.open-meteo.com/v1/forecast'
MAX_BUSES = 4
MAX_CONFIG_SIZE = 10240

_cache = {}
CACHE_TTL = 10
WEATHER_CACHE_TTL = 3600


def get_cached(key, ttl=CACHE_TTL):
    entry = _cache.get(key)
    if entry and time.time() - entry['time'] < ttl:
        return entry['data']
    return None


def set_cache(key, data):
    if len(_cache) > 100:
        oldest = min(_cache, key=lambda k: _cache[k]['time'])
        del _cache[oldest]
    _cache[key] = {'data': data, 'time': time.time()}


def sanitize_id(val):
    """Strip non-digit characters from a query parameter."""
    if val is None:
        return None
    cleaned = ''.join(c for c in str(val) if c.isdigit())
    return cleaned if cleaned else None


def sanitize_coord(val):
    """Validate and sanitize a coordinate query parameter."""
    if val is None:
        return None
    cleaned = ''.join(c for c in str(val) if c.isdigit() or c in '.+-')
    try:
        f = float(cleaned)
        if -180 <= f <= 180:
            return str(f)
    except ValueError:
        pass
    return None


def proxy_fetch(url, cache_key, timeout=6):
    """Fetch JSON from an upstream API with caching."""
    cached = get_cached(cache_key)
    if cached:
        return cached
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        set_cache(cache_key, data)
        return data
    except requests.Timeout:
        raise Exception('Upstream timeout')
    except requests.RequestException as e:
        raise Exception(f'Upstream error: {e}')


@app.route('/api/agencies')
def get_agencies():
    try:
        data = proxy_fetch(f'{TRANSLOC_BASE}/agencies', 'agencies')
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': 'Failed to fetch agencies', 'detail': str(e)}), 502


@app.route('/api/routes')
def get_routes():
    agency = sanitize_id(request.args.get('agency'))
    if not agency:
        return jsonify({'error': 'Missing or invalid agency parameter'}), 400
    try:
        data = proxy_fetch(f'{TRANSLOC_BASE}/routes?agencies={agency}', f'routes-{agency}')
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': 'Failed to fetch routes', 'detail': str(e)}), 502


@app.route('/api/arrivals')
def get_arrivals():
    route = sanitize_id(request.args.get('route'))
    stop = sanitize_id(request.args.get('stop'))
    if not route:
        return jsonify({'error': 'Missing or invalid route parameter'}), 400
    try:
        url = f'{TRANSLOC_BASE}/arrivals?routes={route}'
        key = f'arrivals-{route}'
        if stop:
            url += f'&stops={stop}'
            key += f'-{stop}'
        data = proxy_fetch(url, key)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': 'Failed to fetch arrivals', 'detail': str(e)}), 502


@app.route('/api/vehicles')
def get_vehicles():
    agency = sanitize_id(request.args.get('agency'))
    route = sanitize_id(request.args.get('route'))
    if not agency or not route:
        return jsonify({'error': 'Missing or invalid agency/route parameter'}), 400
    try:
        url = f'{TRANSLOC_BASE}/vehicle_statuses?agencies={agency}&routes={route}'
        data = proxy_fetch(url, f'vehicles-{agency}-{route}')
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': 'Failed to fetch vehicles', 'detail': str(e)}), 502


@app.route('/api/weather')
def get_weather():
    lat = sanitize_coord(request.args.get('lat'))
    lon = sanitize_coord(request.args.get('lon'))
    if not lat or not lon:
        return jsonify({'error': 'Missing or invalid lat/lon parameter'}), 400
    try:
        cache_key = f'weather-{lat}-{lon}'
        cached = get_cached(cache_key, WEATHER_CACHE_TTL)
        if cached:
            return jsonify(cached)

        weather_url = (
            f'{WEATHER_BASE}?latitude={lat}&longitude={lon}'
            f'&current=temperature_2m'
            f'&temperature_unit=celsius'
        )
        w_res = requests.get(weather_url, timeout=5)
        w_res.raise_for_status()
        data = w_res.json()

        set_cache(cache_key, data)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': 'Failed to fetch weather', 'detail': str(e)}), 502


def read_config():
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f'Error reading config: {e}')
    return {'buses': []}


def write_config(config):
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=2)


@app.route('/api/config', methods=['GET'])
def get_config():
    return jsonify(read_config())


@app.route('/api/config', methods=['POST'])
def save_config():
    try:
        if request.content_length and request.content_length > MAX_CONFIG_SIZE:
            return jsonify({'error': 'Config too large'}), 413
        config = request.get_json()
        if not config or not isinstance(config.get('buses'), list):
            return jsonify({'error': 'Invalid config: must have buses array'}), 400
        if len(config['buses']) > MAX_BUSES:
            return jsonify({'error': f'Maximum {MAX_BUSES} buses allowed'}), 400
        clean_buses = []
        allowed_keys = {'agencyId', 'agencyName', 'agencyLat', 'agencyLon',
                        'routeId', 'routeName', 'stopId', 'stopName',
                        'color', 'description'}
        for bus in config['buses']:
            clean_buses.append({k: v for k, v in bus.items() if k in allowed_keys})
        write_config({'buses': clean_buses})
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': 'Failed to save config', 'detail': str(e)}), 500


@app.route('/settings')
def settings_page():
    return send_from_directory('public', 'settings.html')


if __name__ == '__main__':
    print(f'TransLoc Kiosk Server running at http://0.0.0.0:{PORT}')
    print(f'Settings page: http://localhost:{PORT}/settings')
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
