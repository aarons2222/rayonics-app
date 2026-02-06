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
import os
import signal
import sys
import webbrowser
from pathlib import Path

import websockets
from websockets.http import Headers

from ble_handler import BLEHandler

HOST = "localhost"
PORT = 8765
STATIC_DIR = Path(__file__).parent / "static"

# MIME type map for static files
MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}


# ── HTTP handler (serves static files) ────────────────────────────────────

async def http_handler(path: str, request_headers: Headers):
    """
    Called by websockets for every incoming HTTP request that is NOT
    an Upgrade (i.e. not a WebSocket handshake). We use it to serve
    static files so we don't need a separate HTTP framework.
    """
    # Strip query string
    path = path.split("?")[0]

    # Default to index.html
    if path == "/":
        path = "/index.html"

    # Only serve from static/
    file_path = (STATIC_DIR / path.lstrip("/")).resolve()

    # Security: must be inside STATIC_DIR
    try:
        file_path.relative_to(STATIC_DIR.resolve())
    except ValueError:
        return (403, {}, b"Forbidden")

    if not file_path.is_file():
        return (404, {}, b"Not found")

    ext = file_path.suffix.lower()
    content_type = MIME_TYPES.get(ext, "application/octet-stream")
    body = file_path.read_bytes()

    return (200, {"Content-Type": content_type}, body)


# ── WebSocket handler ─────────────────────────────────────────────────────

async def ws_handler(websocket):
    """Handle a single WebSocket connection."""
    print(f"[ws] Client connected from {websocket.remote_address}")

    async def send_json(msg: dict):
        await websocket.send(json.dumps(msg))

    handler = BLEHandler(send=send_json)

    try:
        async for raw in websocket:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await send_json({"type": "error", "message": "Invalid JSON"})
                continue
            await handler.handle(msg)
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        # Clean up BLE on disconnect
        await handler.disconnect(silent=True)
        print(f"[ws] Client disconnected")


# ── Main ──────────────────────────────────────────────────────────────────

async def main():
    no_open = "--no-open" in sys.argv

    print(f"Rayonics Key Reader")
    print(f"  HTTP  → http://{HOST}:{PORT}")
    print(f"  WS    → ws://{HOST}:{PORT}/ws")
    print()

    # Start the combined HTTP + WS server
    async with websockets.serve(
        ws_handler,
        HOST,
        PORT,
        process_request=http_handler,
        max_size=2**20,
    ) as server:
        if not no_open:
            webbrowser.open(f"http://{HOST}:{PORT}")

        print("Server running — press Ctrl+C to stop")

        # Wait forever (until Ctrl-C)
        stop = asyncio.Future()

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop.set_result, None)
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                pass

        try:
            await stop
        except asyncio.CancelledError:
            pass

    print("\nServer stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
