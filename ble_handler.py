"""
Rayonics BLE Handler — bridges WebSocket commands to BLE operations.

All crypto/protocol logic lives in rayonics_ble/. This module wraps
the SDK with a JSON-message interface suitable for the WebSocket server.
"""

import asyncio
import json
import random
import string
import traceback
from typing import Callable, Optional

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

from rayonics_ble.constants import (
    SERVICE_UUID, WRITE_CHAR, NOTIFY_CHAR,
    DEVICE_PREFIXES, Command,
)
from rayonics_ble.crypto import (
    aes_decrypt, build_packet, crc16, derive_session_key_v2, parse_packet,
)

# ── Auth codes (server-side only — never sent to the browser) ─────────────
SYSCODE = bytes([0x11, 0x11, 0x1B, 0xFB])
REGCODE = bytes([0x11, 0x11, 0x1B, 0xFB])

# Map event type ints to human-readable names
EVENT_TYPE_NAMES = {
    0: "Unknown",
    1: "Open Success",
    2: "Open Fail",
    3: "Set Success",
    4: "Set Fail",
    5: "No Permission",
    6: "Blacklisted",
    7: "Time Expired",
    8: "Outside Schedule",
    9: "Read Audit",
    10: "Read Blacklist",
    11: "Sequence Open",
    12: "Sequence Cancel",
    13: "Emergency Open",
    14: "Power On",
    15: "Low Battery",
    16: "Tamper",
    17: "Lock Locked",
    18: "Lock Unlocked",
}

# Map key type ints to names
KEY_TYPE_NAMES = {
    0x00: "Blank",
    0x06: "LSD4BT",
    0x11: "Register",
    0x12: "Setting",
    0x13: "Audit",
    0x15: "Blacklist",
    0x16: "Auxiliary",
    0x17: "Advanced",
    0x20: "Verify",
    0x21: "Trace",
    0x25: "Construction",
    0x50: "User",
    0xF2: "Logout",
    0xF5: "Electricity",
    0xF6: "Emergency",
}


class BLEHandler:
    """Manages a single BLE connection and translates WS commands."""

    def __init__(self, send: Callable):
        """
        Args:
            send: async callable that pushes a JSON-serialisable dict
                  back to the WebSocket client.
        """
        self._send = send
        self._client: Optional[BleakClient] = None
        self._device: Optional[BLEDevice] = None
        self._session_key: Optional[bytes] = None
        self._authenticated = False
        self._response = bytearray()
        self._response_event = asyncio.Event()
        # Keep scanned devices so we can look up by address
        self._scanned: dict[str, BLEDevice] = {}

    # ── helpers ────────────────────────────────────────────────────────────

    async def _emit(self, msg: dict):
        await self._send(msg)

    async def _log(self, message: str, level: str = "info"):
        await self._emit({"type": "log", "message": message, "level": level})

    async def _error(self, message: str):
        await self._emit({"type": "error", "message": message})

    async def _status(self):
        connected = self._client is not None and self._client.is_connected
        name = (self._device.name or self._device.address) if self._device else ""
        await self._emit({
            "type": "status",
            "connected": connected,
            "authenticated": self._authenticated,
            "device": name,
        })

    def _on_notify(self, _sender, data: bytearray):
        self._response.extend(data)
        self._response_event.set()

    async def _send_cmd(self, cmd: int, payload: bytes = b"",
                        timeout: float = 3.0) -> Optional[bytes]:
        """Send an encrypted command and return the raw 16-byte decrypted response."""
        if not self._client or not self._client.is_connected:
            raise RuntimeError("Not connected")

        key = self._session_key  # None → system key inside build_packet
        packet = build_packet(cmd, payload, key=key)

        self._response.clear()
        self._response_event.clear()

        await self._client.write_gatt_char(WRITE_CHAR, packet, response=False)

        await asyncio.wait_for(self._response_event.wait(), timeout=timeout)
        resp = bytes(self._response)
        if len(resp) < 19:
            return None
        return aes_decrypt(resp[1:17], key or b"RAYONICSBLEKEYV2")

    # ── public dispatch ───────────────────────────────────────────────────

    async def handle(self, msg: dict):
        """Route an incoming WS message to the right handler."""
        action = msg.get("action")
        try:
            if action == "scan":
                await self.scan()
            elif action == "connect":
                await self.connect(msg["address"])
            elif action == "disconnect":
                await self.disconnect()
            elif action == "read_key":
                await self.read_key()
            elif action == "read_events":
                await self.read_events(clear=msg.get("clear", False))
            elif action == "clear_events":
                await self.clear_events()
            else:
                await self._error(f"Unknown action: {action}")
        except Exception as exc:
            await self._error(f"{type(exc).__name__}: {exc}")
            traceback.print_exc()

    # ── scan ──────────────────────────────────────────────────────────────

    async def scan(self):
        await self._log("Scanning for BLE devices…")
        self._scanned.clear()
        found = []

        devices = await BleakScanner.discover(timeout=5.0, return_adv=True)
        for _addr, (dev, adv) in devices.items():
            name = dev.name or adv.local_name or ""
            if not any(name.startswith(p) for p in DEVICE_PREFIXES):
                continue
            self._scanned[dev.address] = dev
            found.append({
                "name": name,
                "address": dev.address,
                "rssi": adv.rssi or -100,
            })

        await self._log(f"Found {len(found)} device(s)")
        await self._emit({"type": "devices", "devices": found})

    # ── connect + authenticate ────────────────────────────────────────────

    async def connect(self, address: str):
        # Disconnect previous if any
        await self.disconnect(silent=True)

        device = self._scanned.get(address)
        if device is None:
            await self._error(f"Device {address} not in scan results — scan first")
            return

        await self._log(f"Connecting to {device.name or address}…")
        try:
            self._client = BleakClient(device)
            await self._client.connect()
            self._device = device
        except Exception as exc:
            self._client = None
            self._device = None
            await self._error(f"Connection failed: {exc}")
            return

        await self._log("Connected — subscribing to notifications…")
        await self._client.start_notify(NOTIFY_CHAR, self._on_notify)
        await asyncio.sleep(0.2)

        # ── CONNECT (0x0D) ─────────────────────────────────────────────────
        await self._log("Sending CONNECT (0x0D)…")
        nonce = "".join(random.choices(string.ascii_letters + string.digits, k=10)).encode()
        nonce_crc = crc16(nonce)
        suffix = bytes([nonce_crc & 0xFF, (nonce_crc >> 8) & 0xFF])

        self._response.clear()
        self._response_event.clear()
        packet = build_packet(Command.CONNECT_AUTH, nonce + suffix, key=None, frame=0x01)
        await self._client.write_gatt_char(WRITE_CHAR, packet, response=False)

        try:
            await asyncio.wait_for(self._response_event.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            await self._error("CONNECT timed out")
            await self.disconnect(silent=True)
            return

        resp = bytes(self._response)
        if len(resp) < 19:
            await self._error("Bad CONNECT response (short)")
            await self.disconnect(silent=True)
            return

        decrypted = aes_decrypt(resp[1:17], b"RAYONICSBLEKEYV2")
        resp_length = decrypted[0]

        if resp_length != 15:
            error_code = decrypted[2] if len(decrypted) > 2 else 0xFF
            await self._error(f"CONNECT rejected (len={resp_length}, err=0x{error_code:02X})")
            await self.disconnect(silent=True)
            return

        seed = decrypted[2:14]
        self._session_key = derive_session_key_v2(nonce, suffix, seed, SYSCODE, REGCODE)
        await self._log("Session key derived ✓")

        await asyncio.sleep(0.3)

        # ── VERIFY (0x0F) ──────────────────────────────────────────────────
        await self._log("Sending VERIFY (0x0F)…")
        self._response.clear()
        self._response_event.clear()
        verify_payload = REGCODE + SYSCODE + bytes([0x04])
        packet = build_packet(Command.VERIFY_CODE, verify_payload, key=self._session_key)
        await self._client.write_gatt_char(WRITE_CHAR, packet, response=False)

        try:
            await asyncio.wait_for(self._response_event.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            await self._error("VERIFY timed out")
            await self.disconnect(silent=True)
            return

        resp = bytes(self._response)
        if len(resp) >= 19:
            dec = aes_decrypt(resp[1:17], self._session_key)
            if dec[2] == 0x00:
                self._authenticated = True
                await self._log("Authentication successful ✓")
            else:
                await self._error(f"VERIFY failed (code=0x{dec[2]:02X})")
                await self.disconnect(silent=True)
                return
        else:
            await self._error("Bad VERIFY response")
            await self.disconnect(silent=True)
            return

        await asyncio.sleep(0.2)
        await self._status()

    # ── disconnect ────────────────────────────────────────────────────────

    async def disconnect(self, silent: bool = False):
        if self._client and self._client.is_connected:
            try:
                await self._client.disconnect()
            except Exception:
                pass
        self._client = None
        self._device = None
        self._session_key = None
        self._authenticated = False
        if not silent:
            await self._log("Disconnected")
            await self._status()

    # ── read key info ─────────────────────────────────────────────────────

    async def read_key(self):
        if not self._authenticated:
            await self._error("Not authenticated — connect first")
            return

        await self._log("Reading key info (0x11)…")
        dec = await self._send_cmd(Command.GET_KEY_INFO, b"")
        if dec is None:
            await self._error("GET_KEY_INFO timed out")
            return

        payload_len = dec[0] - 3
        p = dec[2 : 2 + payload_len]

        key_type = p[2] if len(p) > 2 else 0
        data = {
            "keyId": (p[0] | (p[1] << 8)) if len(p) > 1 else 0,
            "keyType": key_type,
            "keyTypeName": KEY_TYPE_NAMES.get(key_type, f"0x{key_type:02X}"),
            "groupId": (p[3] | (p[4] << 8)) if len(p) > 4 else 0,
            "verifyDay": (p[6] | (p[7] << 8)) if len(p) > 7 else 0,
            "isBleOnline": p[8] if len(p) > 8 else 0,
            "power": p[9] if len(p) > 9 else 0,
        }

        await self._log("Key info received ✓")

        # Also grab version
        await asyncio.sleep(0.2)
        await self._log("Reading version (0x34)…")
        dec2 = await self._send_cmd(0x34, b"")
        version = ""
        if dec2 is not None:
            vp = dec2[2 : dec2[0]]
            for b in vp:
                if b == 0 or b > 127:
                    break
                version += chr(b)
        data["version"] = version
        await self._log(f"Version: {version}")

        await self._emit({"type": "key_info", "data": data})

    # ── read events ───────────────────────────────────────────────────────

    async def read_events(self, clear: bool = False):
        if not self._authenticated:
            await self._error("Not authenticated — connect first")
            return

        await self._log("Getting event count (0x26)…")
        dec = await self._send_cmd(Command.GET_EVENT_COUNT, b"")
        if dec is None:
            await self._error("GET_EVENT_COUNT timed out")
            return

        count = dec[2] | (dec[3] << 8)
        await self._log(f"Event count: {count}")
        await asyncio.sleep(0.2)

        events = []
        for pos in range(1, count + 1):
            pos_bytes = bytes([pos & 0xFF, (pos >> 8) & 0xFF])
            try:
                dec = await self._send_cmd(Command.GET_EVENT, pos_bytes)
                if dec is not None:
                    elen = dec[0] - 3
                    ed = dec[2 : 2 + elen]
                    events.append(self._parse_event(ed))
                else:
                    events.append({"pos": pos, "error": "timeout"})
            except Exception as exc:
                events.append({"pos": pos, "error": str(exc)})
            await asyncio.sleep(0.15)

        await self._log(f"Read {len(events)} event(s) ✓")
        await self._emit({"type": "events", "data": events})

        if clear and count > 0:
            await self.clear_events()

    # ── clear events ──────────────────────────────────────────────────────

    async def clear_events(self):
        if not self._authenticated:
            await self._error("Not authenticated — connect first")
            return

        await self._log("Clearing events (0x28)…")
        dec = await self._send_cmd(Command.CLEAN_EVENT, b"")
        if dec is not None:
            await self._log("Events cleared ✓")
        else:
            await self._error("CLEAN_EVENT timed out")

    # ── event parser ──────────────────────────────────────────────────────

    @staticmethod
    def _parse_event(data: bytes) -> dict:
        if len(data) < 12:
            return {"raw": data.hex()}

        def bcd(b):
            return ((b >> 4) * 10) + (b & 0x0F)

        key_id = data[0] | (data[1] << 8)
        lock_id = data[3] | (data[4] << 8)

        year = 2000 + bcd(data[5])
        month = bcd(data[6])
        day = bcd(data[7])
        hour = bcd(data[8])
        minute = bcd(data[9])
        second = bcd(data[10])
        event_type = data[11]

        return {
            "time": f"{year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}",
            "lockId": lock_id,
            "keyId": key_id,
            "event": event_type,
            "eventName": EVENT_TYPE_NAMES.get(event_type, f"Unknown ({event_type})"),
        }
