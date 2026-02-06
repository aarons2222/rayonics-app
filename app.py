#!/usr/bin/env python3
"""
Rayonics Key Reader — GUI launcher.

A simple tkinter window that starts/stops the server
and shows the log output. Opens the browser automatically.
"""

import asyncio
import json
import queue
import sys
import threading
import tkinter as tk
from tkinter import scrolledtext
import webbrowser
from datetime import datetime
from pathlib import Path

from aiohttp import web

from ble_handler import BLEHandler

HOST = "localhost"
PORT = 8765
STATIC_DIR = Path(__file__).parent / "static"


class WebServer:
    """Async web server that can be started/stopped from another thread."""

    def __init__(self, log_queue: queue.Queue):
        self._log = log_queue
        self._runner = None
        self._loop = None
        self._thread = None
        self.running = False

    def log(self, msg: str, level: str = "info"):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log.put((ts, msg, level))

    async def _ws_handler(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.log(f"Client connected from {request.remote}")

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
                    # Log actions
                    action = data.get("action", "?")
                    if action not in ("set_codes",):
                        self.log(f"← {action}", "info")
                    await handler.handle(data)
                elif msg.type == web.WSMsgType.ERROR:
                    self.log(f"WS error: {ws.exception()}", "error")
        finally:
            await handler.disconnect(silent=True)
            self.log("Client disconnected")

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
        self.log(f"Server started on http://{HOST}:{PORT}", "success")

        # Keep running until cancelled
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await self._runner.cleanup()
            self.running = False
            self.log("Server stopped", "info")

    def start(self):
        if self._thread and self._thread.is_alive():
            return

        def run():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._task = self._loop.create_task(self._run())
            try:
                self._loop.run_until_complete(self._task)
            except Exception as e:
                self.log(f"Server error: {e}", "error")
            finally:
                self._loop.close()
                self._loop = None
                self.running = False

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def stop(self):
        if self._loop and self._task:
            self._loop.call_soon_threadsafe(self._task.cancel)


class App:
    """Tkinter GUI for the server."""

    BG = "#0f1117"
    SURFACE = "#1a1d27"
    BORDER = "#2a2d3a"
    TEXT = "#e0e0e8"
    DIM = "#8888a0"
    ACCENT = "#5b8def"
    GREEN = "#3ecf8e"
    RED = "#ef5b5b"
    WARN = "#f0b840"
    FONT = ("SF Mono", 11) if sys.platform == "darwin" else ("Consolas", 10)
    FONT_UI = ("SF Pro Display", 13) if sys.platform == "darwin" else ("Segoe UI", 11)

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Rayonics Key Reader")
        self.root.configure(bg=self.BG)
        self.root.geometry("700x500")
        self.root.minsize(500, 350)

        self.log_queue = queue.Queue()
        self.server = WebServer(self.log_queue)

        self._build_ui()
        self._poll_log()

        # Auto-start server
        self.start_server()

    def _build_ui(self):
        # ── Top bar ──
        top = tk.Frame(self.root, bg=self.SURFACE, padx=16, pady=10)
        top.pack(fill=tk.X)

        tk.Label(
            top, text="🔑 Rayonics Key Reader", font=(self.FONT_UI[0], 15, "bold"),
            bg=self.SURFACE, fg=self.TEXT
        ).pack(side=tk.LEFT)

        self.status_dot = tk.Label(top, text="●", font=(self.FONT_UI[0], 14),
                                   bg=self.SURFACE, fg=self.RED)
        self.status_dot.pack(side=tk.RIGHT, padx=(8, 0))

        self.status_label = tk.Label(top, text="Stopped", font=self.FONT_UI,
                                     bg=self.SURFACE, fg=self.DIM)
        self.status_label.pack(side=tk.RIGHT)

        # ── Separator ──
        tk.Frame(self.root, bg=self.BORDER, height=1).pack(fill=tk.X)

        # ── Button bar ──
        bar = tk.Frame(self.root, bg=self.BG, padx=16, pady=10)
        bar.pack(fill=tk.X)

        self.btn_toggle = tk.Button(
            bar, text="⏹ Stop Server", font=self.FONT_UI,
            bg=self.ACCENT, fg="white", activebackground="#4a7cde",
            relief=tk.FLAT, padx=16, pady=4, cursor="hand2",
            command=self.toggle_server
        )
        self.btn_toggle.pack(side=tk.LEFT)

        self.btn_browser = tk.Button(
            bar, text="🌐 Open Browser", font=self.FONT_UI,
            bg=self.SURFACE, fg=self.TEXT, activebackground=self.BORDER,
            relief=tk.FLAT, padx=16, pady=4, cursor="hand2",
            command=self.open_browser
        )
        self.btn_browser.pack(side=tk.LEFT, padx=(8, 0))

        self.btn_clear = tk.Button(
            bar, text="Clear Log", font=self.FONT_UI,
            bg=self.SURFACE, fg=self.DIM, activebackground=self.BORDER,
            relief=tk.FLAT, padx=12, pady=4, cursor="hand2",
            command=self.clear_log
        )
        self.btn_clear.pack(side=tk.RIGHT)

        # ── Log area ──
        log_frame = tk.Frame(self.root, bg=self.BG, padx=16, pady=(0, 16))
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_area = scrolledtext.ScrolledText(
            log_frame, font=self.FONT, bg="#0a0a0f", fg=self.DIM,
            insertbackground=self.TEXT, relief=tk.FLAT, padx=10, pady=8,
            state=tk.DISABLED, wrap=tk.WORD, borderwidth=0,
            highlightthickness=1, highlightbackground=self.BORDER,
            highlightcolor=self.ACCENT
        )
        self.log_area.pack(fill=tk.BOTH, expand=True)

        # Tag colours for log levels
        self.log_area.tag_configure("info", foreground=self.DIM)
        self.log_area.tag_configure("success", foreground=self.GREEN)
        self.log_area.tag_configure("error", foreground=self.RED)
        self.log_area.tag_configure("warn", foreground=self.WARN)
        self.log_area.tag_configure("time", foreground="#555566")

    def _poll_log(self):
        """Pull messages from the queue into the text widget."""
        while True:
            try:
                ts, msg, level = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self.log_area.configure(state=tk.NORMAL)
            self.log_area.insert(tk.END, f"{ts} ", "time")
            self.log_area.insert(tk.END, f"{msg}\n", level)
            self.log_area.configure(state=tk.DISABLED)
            self.log_area.see(tk.END)

        # Update status indicator
        if self.server.running:
            self.status_dot.configure(fg=self.GREEN)
            self.status_label.configure(text=f"Running — localhost:{PORT}")
            self.btn_toggle.configure(text="⏹ Stop Server", bg=self.RED)
        else:
            self.status_dot.configure(fg=self.RED)
            self.status_label.configure(text="Stopped")
            self.btn_toggle.configure(text="▶ Start Server", bg=self.GREEN)

        self.root.after(100, self._poll_log)

    def start_server(self):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_queue.put((ts, "Starting server...", "info"))
        self.server.start()
        # Auto-open browser after a short delay
        self.root.after(1500, self.open_browser)

    def stop_server(self):
        self.server.stop()

    def toggle_server(self):
        if self.server.running:
            self.stop_server()
        else:
            self.start_server()

    def open_browser(self):
        if self.server.running:
            webbrowser.open(f"http://{HOST}:{PORT}")

    def clear_log(self):
        self.log_area.configure(state=tk.NORMAL)
        self.log_area.delete("1.0", tk.END)
        self.log_area.configure(state=tk.DISABLED)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
