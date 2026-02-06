# Rayonics Key Reader

Desktop app that reads and manages Rayonics BLE smart keys via a local web UI.

A Python WebSocket server handles all BLE communication and cryptography; the browser-based frontend just sends commands and displays results.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run
python server.py
```

The server starts on `http://localhost:8765` and auto-opens your browser.

## Usage

1. **Scan** — click the scan button to discover nearby Rayonics keys
2. **Connect** — click a device to connect (handles CONNECT + VERIFY authentication)
3. **Read Key** — reads key ID, type, group, battery, version
4. **Read Events** — reads all stored events (timestamps, lock IDs, event types)
5. **Clear Events** — check "Clear after read" to wipe events after reading (like the official app)
6. **Disconnect** — cleanly disconnects from the key

## Architecture

```
┌──────────────┐      WebSocket       ┌──────────────┐       BLE        ┌────────────┐
│   Browser    │◄────────────────────►│  server.py   │◄───────────────►│  BLE Key   │
│  (static/)   │   JSON messages      │ ble_handler  │   Encrypted     │  (B03009)  │
│  No crypto   │                      │ rayonics_ble │   protocol      │            │
└──────────────┘                      └──────────────┘                  └────────────┘
```

- **server.py** — HTTP + WebSocket server (serves static files + handles WS)
- **ble_handler.py** — translates WS commands to BLE operations
- **rayonics_ble/** — crypto, packet building, protocol constants (copied from SDK)
- **static/** — HTML/CSS/JS frontend (dark theme, no frameworks)

## Building a Standalone Executable

```bash
pip install pyinstaller
python build.py
```

Creates `dist/RayonicsKeyReader` (or `.exe` on Windows) — a single file that bundles everything.

## Protocol Notes

- AES-128-ECB encrypted 19-byte packets over BLE
- CRC16-KERMIT checksums + XOR integrity bytes
- Session key derived from random nonce ⊕ device seed + syscode + CRC
- VERIFY command completes the authentication handshake
- Events use 1-based indexing with BCD timestamps
- **No reset commands are exposed** — this tool only reads

## Requirements

- Python 3.9+
- macOS / Linux / Windows (BLE adapter required)
- Dependencies: `bleak`, `websockets`, `pycryptodome`
