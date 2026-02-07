#!/usr/bin/env python3
"""
Rayonics Key Reader — System tray / menu bar app.

Sits quietly in the menu bar (macOS) or system tray (Windows/Linux).
Runs the WebSocket server in the background.
"""

import asyncio
import json
import sys
import threading
import webbrowser
from pathlib import Path

from aiohttp import web

from ble_handler import BLEHandler

# Use rumps on macOS for native menu bar, pystray elsewhere
if sys.platform == "darwin":
    try:
        import rumps
        USE_RUMPS = True
        # Hide dock icon — make this a menu bar-only app
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    except ImportError:
        USE_RUMPS = False
else:
    USE_RUMPS = False

if not USE_RUMPS:
    import pystray

HOST = "localhost"
PORT = 8765

# When running from PyInstaller bundle, files are in sys._MEIPASS
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
ASSETS_DIR = BASE_DIR / "assets"


# ── Web Server ────────────────────────────────────────────────────────────

class WebServer:
    """Async web server running in a background thread."""

    def __init__(self):
        self._runner = None
        self._loop = None
        self._thread = None
        self._task = None
        self.running = False

    async def _ws_handler(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)

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
                    pass
        finally:
            await handler.disconnect(silent=True)

        return ws

    async def _index_handler(self, request):
        return web.FileResponse(STATIC_DIR / "index.html")

    def _create_app(self):
        app = web.Application()
        app.router.add_get("/ws", self._ws_handler)
        app.router.add_get("/", self._index_handler)
        app.router.add_static("/", STATIC_DIR)
        return app

    async def _run(self):
        app = self._create_app()
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, HOST, PORT)
        await site.start()
        self.running = True

        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            try:
                await self._runner.cleanup()
            except BaseException:
                pass
            self.running = False

    def start(self):
        if self._thread and self._thread.is_alive():
            return

        def run():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._task = self._loop.create_task(self._run())
            try:
                self._loop.run_until_complete(self._task)
            except Exception:
                pass
            finally:
                self._loop.close()
                self._loop = None
                self.running = False

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def stop(self):
        if self._loop and self._task:
            self.running = False  # Mark stopped immediately
            self._loop.call_soon_threadsafe(self._task.cancel)


server = WebServer()


# ── macOS menu bar (rumps) ────────────────────────────────────────────────

if USE_RUMPS:

    class TrayApp(rumps.App):
        def __init__(self):
            icon_path = str(ASSETS_DIR / "menubarTemplate.png")
            super().__init__(
                "eLOQ Sync",
                icon=icon_path,
                quit_button=None,
                template=True,
            )

            self.menu = [
                rumps.MenuItem("🟢 Server Running", callback=None),
                rumps.MenuItem(f"    Port: {PORT}", callback=None),
                None,  # separator
                rumps.MenuItem("Open Browser", callback=self.open_browser),
                None,
                rumps.MenuItem("Stop Server", callback=self.toggle_server),
                None,
                rumps.MenuItem("Quit", callback=self.quit_app),
            ]
            self._status_item = self.menu["🟢 Server Running"]
            self._status_item.set_callback(None)
            self._port_item = self.menu[f"    Port: {PORT}"]
            self._port_item.set_callback(None)
            self._toggle_item = self.menu["Stop Server"]

            # Start server
            server.start()

            # Poll status
            self._timer = rumps.Timer(self._check_status, 1)
            self._timer.start()

        def _check_status(self, _):
            if server.running:
                self._status_item.title = "🟢 Server Running"
                self._port_item.title = f"    http://localhost:{PORT}"
                self._toggle_item.title = "⏹ Stop Server"
                self.title = ""
            else:
                self._status_item.title = "🔴 Server Stopped"
                self._port_item.title = ""
                self._toggle_item.title = "▶ Start Server"
                self.title = ""

        def toggle_server(self, _):
            if server.running:
                server.stop()
            else:
                server.start()
                # Open browser after a delay
                def delayed_open():
                    import time
                    time.sleep(1.5)
                    if server.running:
                        webbrowser.open(f"http://{HOST}:{PORT}")
                threading.Thread(target=delayed_open, daemon=True).start()

        def open_browser(self, _):
            if server.running:
                webbrowser.open(f"http://{HOST}:{PORT}")

        def quit_app(self, _):
            server.stop()
            rumps.quit_application()

    def main():
        # Auto-open browser after server starts
        def delayed_open():
            import time
            time.sleep(2)
            if server.running:
                webbrowser.open(f"http://{HOST}:{PORT}")

        threading.Thread(target=delayed_open, daemon=True).start()
        TrayApp().run()


# ── Cross-platform system tray (pystray) ─────────────────────────────────

else:

    def on_open(icon, item):
        if server.running:
            webbrowser.open(f"http://{HOST}:{PORT}")

    def on_quit(icon, item):
        server.stop()
        icon.stop()

    def get_status_text():
        return f"Server: Running (:{PORT})" if server.running else "Server: Stopped"

    def main():
        from PIL import Image
        server.start()

        from PIL import Image as PILImage
        tray_icon = PILImage.open(ASSETS_DIR / "icon.png")
        icon = pystray.Icon(
            "eloq-sync",
            tray_icon,
            "eLOQ Sync",
            menu=pystray.Menu(
                pystray.MenuItem("Open Browser", on_open, default=True),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(get_status_text, None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", on_quit),
            ),
        )

        # Auto-open browser
        def delayed_open():
            import time
            time.sleep(2)
            if server.running:
                webbrowser.open(f"http://{HOST}:{PORT}")

        threading.Thread(target=delayed_open, daemon=True).start()
        icon.run()


if __name__ == "__main__":
    main()
