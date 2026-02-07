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
        self.ble_active = False  # True during BLE operations (scan/connect/read)
        self._port_error = None  # Set if port is already in use
        self._ws_clients: set = set()  # Track active WebSocket connections

    async def _ws_handler(self, request):
        origin = request.headers.get("Origin", "")
        if origin and origin not in ALLOWED_ORIGINS:
            return web.Response(status=403, text="Forbidden: origin not allowed")

        ws = web.WebSocketResponse(heartbeat=5.0)  # ping every 5s to detect dead connections
        await ws.prepare(request)

        self._ws_clients.add(ws)
        srv = self  # reference for activity flag

        async def send_json(msg: dict):
            if not ws.closed:
                await ws.send_str(json.dumps(msg))
                # Track BLE activity from message types
                mtype = msg.get("type", "")
                if mtype in ("devices", "key_info", "events", "status"):
                    srv.ble_active = False  # operation completed

        handler = BLEHandler(send=send_json)

        # BLE actions that indicate activity
        ACTIVE_ACTIONS = {"scan", "connect", "read_key", "read_events", "clear_events"}

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                    except json.JSONDecodeError:
                        await send_json({"type": "error", "message": "Invalid JSON"})
                        continue
                    if data.get("action") in ACTIVE_ACTIONS:
                        srv.ble_active = True
                    await handler.handle(data)
                elif msg.type == web.WSMsgType.ERROR:
                    pass
        finally:
            srv.ble_active = False
            self._ws_clients.discard(ws)
            await handler.disconnect(silent=True)

        return ws

    async def _index_handler(self, request):
        return web.FileResponse(STATIC_DIR / "index.html")

    async def _version_handler(self, request):
        from rayonics_ble import __version__
        return web.json_response({"version": __version__})

    def _create_app(self):
        app = web.Application()
        app.router.add_get("/ws", self._ws_handler)
        app.router.add_get("/api/version", self._version_handler)
        app.router.add_get("/", self._index_handler)
        app.router.add_static("/", STATIC_DIR)
        return app

    async def _run(self):
        app = self._create_app()
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, HOST, PORT)
        try:
            await site.start()
        except OSError as exc:
            self._port_error = str(exc)
            self.running = False
            return
        self._port_error = None
        self.running = True

        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            # Close all WebSocket clients with a proper close frame
            for ws in list(self._ws_clients):
                try:
                    await ws.close(code=1001, message=b"Server shutting down")
                except Exception:
                    pass
            self._ws_clients.clear()
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


def check_bluetooth_available() -> tuple[bool, str]:
    """Check if a Bluetooth adapter is available. Returns (available, message)."""
    import asyncio as _asyncio

    async def _check():
        try:
            from bleak import BleakScanner
            # Quick check — just see if scanner can start without error
            scanner = BleakScanner()
            await scanner.start()
            await asyncio.sleep(0.1)
            await scanner.stop()
            return True, "Bluetooth adapter found"
        except Exception as exc:
            err = str(exc).lower()
            if "bluetooth" in err and ("off" in err or "disabled" in err or "not powered" in err):
                return False, "Bluetooth is turned off.\nEnable it in System Settings → Bluetooth."
            elif "not found" in err or "no adapter" in err or "not available" in err:
                return False, "No Bluetooth adapter found.\nPlug in a USB Bluetooth dongle."
            else:
                return False, f"Bluetooth error: {exc}"

    loop = _asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_check())
    finally:
        loop.close()


# ── macOS menu bar (rumps) ────────────────────────────────────────────────

if USE_RUMPS:

    class TrayApp(rumps.App):
        def __init__(self):
            self._icon_normal = str(ASSETS_DIR / "menubarTemplate.png")
            self._icon_active = str(ASSETS_DIR / "menubarActive.png")
            self._flash_on = False

            super().__init__(
                "eLOQ Sync",
                icon=self._icon_normal,
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

            # Server started by main() after Bluetooth check

            # Poll status (0.5s for smooth icon flash)
            self._timer = rumps.Timer(self._check_status, 0.5)
            self._timer.start()

        def _check_status(self, _):
            if server.running:
                self._status_item.title = "🟢 Server Running"
                self._port_item.title = f"    http://localhost:{PORT}"
                self._toggle_item.title = "⏹ Stop Server"

                # Flash icon during BLE activity
                if server.ble_active:
                    self._flash_on = not self._flash_on
                    if self._flash_on:
                        self.icon = self._icon_active
                        self.template = False  # Show colour
                    else:
                        self.icon = self._icon_normal
                        self.template = True
                elif not self.template:
                    # Activity just ended, restore normal icon
                    self.icon = self._icon_normal
                    self.template = True
                    self._flash_on = False

                self.title = ""
            else:
                self._status_item.title = "🔴 Server Stopped"
                self._port_item.title = ""
                self._toggle_item.title = "▶ Start Server"
                self.icon = self._icon_normal
                self.template = True
                self._flash_on = False
                self.title = ""

        def toggle_server(self, _):
            if server.running:
                server.stop()
            else:
                def restart():
                    import time
                    available, msg = check_bluetooth_available()
                    if not available:
                        rumps.alert(
                            title="eLOQ Sync — Bluetooth Required",
                            message=msg,
                            ok="OK",
                        )
                        return
                    server.start()
                    time.sleep(1.5)
                    if server.running:
                        webbrowser.open(f"http://{HOST}:{PORT}")
                threading.Thread(target=restart, daemon=True).start()

        def open_browser(self, _):
            if server.running:
                webbrowser.open(f"http://{HOST}:{PORT}")

        def quit_app(self, _):
            server.stop()
            rumps.quit_application()

    def _check_move_to_applications():
        """Prompt user to move app to /Applications if running from elsewhere."""
        if not getattr(sys, 'frozen', False):
            return  # Running from source, skip

        import os
        app_path = os.path.realpath(sys.executable)
        # PyInstaller .app bundle: executable is inside .app/Contents/MacOS/
        # Walk up to find the .app bundle
        parts = app_path.split(os.sep)
        app_bundle = None
        for i, part in enumerate(parts):
            if part.endswith(".app"):
                app_bundle = os.sep + os.path.join(*parts[:i+1])
                break

        if not app_bundle:
            return

        if app_bundle.startswith("/Applications"):
            return  # Already in Applications

        app_name = os.path.basename(app_bundle)
        dest = f"/Applications/{app_name}"

        resp = rumps.alert(
            title="Move to Applications?",
            message=(
                f"eLOQ Sync is running from:\n{os.path.dirname(app_bundle)}\n\n"
                "Move to Applications folder for easier access?"
            ),
            ok="Move to Applications",
            cancel="Keep Here",
        )

        if resp == 1:  # OK clicked
            try:
                import shutil
                if os.path.exists(dest):
                    shutil.rmtree(dest)
                shutil.move(app_bundle, dest)
                # Relaunch from new location
                import subprocess
                subprocess.Popen(["open", dest])
                rumps.quit_application()
                sys.exit(0)
            except Exception as e:
                rumps.alert(
                    title="Move Failed",
                    message=f"Couldn't move to Applications:\n{e}\n\nDrag the app manually.",
                    ok="OK",
                )

    def main():
        def startup():
            import time

            # Prompt to move to /Applications
            _check_move_to_applications()

            # Check Bluetooth before anything else
            available, msg = check_bluetooth_available()
            if not available:
                rumps.alert(
                    title="eLOQ Sync — Bluetooth Required",
                    message=msg,
                    ok="Quit",
                )
                rumps.quit_application()
                return

            # Start server and open browser
            server.start()
            time.sleep(1.5)
            if server._port_error:
                rumps.alert(
                    title="eLOQ Sync — Port In Use",
                    message=f"Port {PORT} is already in use.\n\nAnother instance may be running, or another app is using this port.",
                    ok="Quit",
                )
                rumps.quit_application()
                return
            if server.running:
                webbrowser.open(f"http://{HOST}:{PORT}")

        threading.Thread(target=startup, daemon=True).start()
        TrayApp().run()


# ── Cross-platform system tray (pystray) ─────────────────────────────────

else:

    def on_open(icon, item):
        if server.running:
            webbrowser.open(f"http://{HOST}:{PORT}")

    def on_quit(icon, item):
        server.stop()
        icon.stop()

    def get_status_text(item=None):
        return f"Server: Running (:{PORT})" if server.running else "Server: Stopped"

    def main():
        # Check Bluetooth before starting
        available, msg = check_bluetooth_available()
        if not available:
            # Show error dialog
            try:
                import tkinter as tk
                from tkinter import messagebox
                root = tk.Tk()
                root.withdraw()
                messagebox.showerror("eLOQ Sync — Bluetooth Required", msg)
                root.destroy()
            except Exception:
                print(f"ERROR: {msg}")
            return

        from PIL import Image as PILImage
        server.start()

        import time as _time
        _time.sleep(1.5)
        if server._port_error:
            try:
                import tkinter as tk
                from tkinter import messagebox
                root = tk.Tk()
                root.withdraw()
                messagebox.showerror("eLOQ Sync — Port In Use", f"Port {PORT} is already in use.\n\nAnother instance may be running.")
                root.destroy()
            except Exception:
                print(f"ERROR: Port {PORT} in use")
            return

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
            time.sleep(1.5)
            if server.running:
                webbrowser.open(f"http://{HOST}:{PORT}")

        threading.Thread(target=delayed_open, daemon=True).start()
        icon.run()


if __name__ == "__main__":
    main()
