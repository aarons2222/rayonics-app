# eLOQ Sync

A desktop app for reading and managing Rayonics BLE smart keys (B03009, LSD4BT).

Runs as a lightweight **menu bar** (macOS) or **system tray** (Windows) app — no terminal, no clutter. Opens a web-based UI in your browser for scanning keys, reading events, and viewing key info.

## Download

**[Latest Release →](https://github.com/aarons2222/eloq-sync/releases/latest)**

| Platform | File | Notes |
|----------|------|-------|
| macOS | `eLOQ-Sync-mac.zip` | Unzip → right-click → **Open** (first launch) |
| Windows | `eLOQ Sync.exe` | Click "More info" → "Run anyway" |

> Both are ad-hoc signed but not notarised. macOS Gatekeeper and Windows SmartScreen will warn on first launch.

## How It Works

```
┌──────────────┐     WebSocket      ┌──────────────┐      BLE       ┌──────────┐
│   Browser    │◄──────────────────►│  Local       │◄──────────────►│ BLE Key  │
│   (any)      │  ws://localhost    │  Server      │  AES-128-ECB   │ (B03009) │
│              │                    │  (this app)  │  encrypted     │          │
└──────────────┘                    └──────────────┘                 └──────────┘
```

1. **Launch the app** — checks for Bluetooth, then sits in your menu bar / system tray
2. **Browser opens** — web UI at `http://localhost:8765`
3. **Scan** — discovers nearby Rayonics keys
4. **Click a device** — connects, authenticates, and reads everything automatically

All data stays local. The browser and server are both on your machine — nothing is transmitted over the internet.

## Features

- **Automatic read** — key info, version, battery, and events load immediately on connect
- **Event log** — timestamps, lock IDs, event types (open, fail, expired, etc.)
- **Clear events** — optionally wipe the event log after reading
- **Configurable codes** — set syscode/regcode in the UI
- **Bluetooth adapter check** — verifies adapter on launch, clear error if missing
- **Menu bar icon flash** — visual feedback during BLE operations
- **Move to Applications** — prompts to install on macOS
- **Cross-platform** — macOS (menu bar) and Windows (system tray)
- **Any browser** — works in Chrome, Edge, Firefox, Safari

## Security

| Segment | Protection |
|---------|-----------|
| BLE Key ↔ Server | AES-128-ECB encrypted |
| Server ↔ Browser | localhost only (never leaves your machine) |
| WebSocket | Origin-checked (only localhost + Vercel UI allowed) |
| No cloud | All data is local. No accounts, no tracking. |

## Running from Source

```bash
git clone https://github.com/aarons2222/eloq-sync.git
cd eloq-sync

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install rumps  # macOS only

# Run
python app.py      # GUI (menu bar / system tray)
python server.py   # CLI (terminal)
```

## Building

```bash
pip install pyinstaller
python build.py          # GUI app
python build.py --cli    # CLI executable
```

Output in `dist/`:
- macOS: `eLOQ Sync.app`
- Windows: `eLOQ Sync.exe`

## Project Structure

```
eloq-sync/
├── app.py              # Menu bar / system tray launcher
├── server.py           # HTTP + WebSocket server (CLI mode)
├── ble_handler.py      # BLE protocol handler
├── rayonics_ble/       # SDK (crypto, constants, models)
├── static/             # Web UI
│   ├── index.html
│   ├── css/style.css
│   └── js/app.js
├── assets/             # App icons
├── build.py            # PyInstaller build script
├── create_icon.py      # Icon generator
└── requirements.txt
```

## Protocol

Supports B03009 encrypted keys:
- **CONNECT** (0x0D) → nonce exchange, session key derivation
- **VERIFY** (0x0F) → syscode/regcode authentication
- **GET_KEY_INFO** (0x11) → key ID, type, group, battery
- **GET_KEY_VERSION** (0x34) → firmware version
- **GET_EVENT_COUNT** (0x26) → event count
- **GET_EVENT** (0x27) → individual events (BCD timestamps)
- **CLEAN_EVENT** (0x2B) → clear event log

## Related

- [rayonics-replacement](https://github.com/aarons2222/rayonics-replacement) — Python SDK (reference library)
- [rayonics-web](https://github.com/aarons2222/rayonics-web) — Hosted web UI ([live](https://rayonics-web.vercel.app))
- [rayonics-gui](https://github.com/aarons2222/rayonics-gui) — PySide6 desktop GUI

## License

MIT
