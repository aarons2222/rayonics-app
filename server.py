#!/usr/bin/env python3
"""
Rayonics Key Reader — local HTTP + WebSocket server.

Serves the web UI on http://localhost:8765 and exposes a WebSocket
at ws://localhost:8765/ws for BLE operations.

Usage:
    python server.py              # starts server + opens browser
    python server.py --no-open    # starts server only
"""

import asyncio
import json
import sys
import webbrowser
from pathlib import Path

from aiohttp import web

from ble_handler import BLEHandler

HOST = "localhost"
PORT = 8765

# Allowed WebSocket origins (prevents drive-by connections from random websites)
ALLOWED_ORIGINS = {
    f"http://localhost:{PORT}",
    f"http://127.0.0.1:{PORT}",
    "https://rayonics-web.vercel.app",
}

# When running from PyInstaller bundle, files are in sys._MEIPASS
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"


# ── WebSocket handler ─────────────────────────────────────────────────────

async def ws_handler(request):
    """Handle a single WebSocket connection."""
    origin = request.headers.get("Origin", "")
    if origin and origin not in ALLOWED_ORIGINS:
        print(f"[ws] Rejected connection from origin: {origin}")
        return web.Response(status=403, text="Forbidden: origin not allowed")

    ws = web.WebSocketResponse(heartbeat=5.0)
    await ws.prepare(request)

    print(f"[ws] Client connected from {request.remote}")

    async def send_json(msg: dict):
        if not ws.closed:
            await ws.send_str(json.dumps(msg))

    handler = BLEHandler(send=send_json)

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except json.JSONDecodeError:
                    await send_json({"type": "error", "message": "Invalid JSON"})
                    continue
                await handler.handle(data)
            elif msg.type == web.WSMsgType.ERROR:
                print(f"[ws] Error: {ws.exception()}")
    finally:
        await handler.disconnect(silent=True)
        print(f"[ws] Client disconnected")

    return ws


# ── Main ──────────────────────────────────────────────────────────────────

async def index_handler(request):
    """Serve index.html for /"""
    return web.FileResponse(STATIC_DIR / "index.html")


async def version_handler(request):
    """Return app version."""
    from rayonics_ble import __version__
    return web.json_response({"version": __version__})


def create_app():
    app = web.Application()

    # WebSocket endpoint
    app.router.add_get("/ws", ws_handler)

    # Version endpoint
    app.router.add_get("/api/version", version_handler)

    # Serve index.html at /
    app.router.add_get("/", index_handler)

    # Static files (css/, js/)
    app.router.add_static("/", STATIC_DIR)

    return app


def main():
    no_open = "--no-open" in sys.argv

    print(f"eLOQ Sync")
    print(f"  HTTP  → http://{HOST}:{PORT}")
    print(f"  WS    → ws://{HOST}:{PORT}/ws")
    print()

    app = create_app()

    if not no_open:
        async def on_startup(_app):
            webbrowser.open(f"http://{HOST}:{PORT}")
        app.on_startup.append(on_startup)

    print("Server running — press Ctrl+C to stop")
    web.run_app(app, host=HOST, port=PORT, print=None)


if __name__ == "__main__":
    main()
