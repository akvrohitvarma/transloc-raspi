#!/usr/bin/env python3
"""
TransLoc Kiosk Launcher

Starts both the Flask server and the Pygame display with a single command.
"""

import subprocess
import sys
import time
import signal
import os
import requests

DIR = os.path.dirname(os.path.abspath(__file__))
server_proc = None
display_proc = None


def cleanup(sig=None, frame=None):
    """Shut down both processes gracefully."""
    print('\nShutting down...')
    for proc, name in [(display_proc, 'Display'), (server_proc, 'Server')]:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
            print(f'  {name} stopped.')
    sys.exit(0)


def wait_for_server(url='http://localhost:3000/api/config', timeout=15):
    """Block until the server responds or timeout is reached."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(url, timeout=2)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def main():
    global server_proc, display_proc

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    python = sys.executable

    print('Starting server...')
    server_proc = subprocess.Popen(
        [python, os.path.join(DIR, 'server.py')],
        cwd=DIR
    )

    print('Waiting for server to be ready...')
    if not wait_for_server():
        print('ERROR: Server did not start in time.')
        cleanup()
        return

    print('Server is ready!')

    print('Starting display...')
    display_proc = subprocess.Popen(
        [python, os.path.join(DIR, 'display.py')],
        cwd=DIR
    )

    while True:
        if server_proc.poll() is not None:
            print(f'Server exited (code {server_proc.returncode})')
            cleanup()
            break
        if display_proc.poll() is not None:
            print(f'Display exited (code {display_proc.returncode})')
            cleanup()
            break
        time.sleep(1)


if __name__ == '__main__':
    main()
