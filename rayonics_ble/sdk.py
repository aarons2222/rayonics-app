"""
Rayonics BLE SDK - Main SDK Class
"""

import asyncio
import os
from typing import Optional, List

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

from .constants import (
    SERVICE_UUID, WRITE_CHAR, NOTIFY_CHAR,
    CHAR_KEY_TYPE, CHAR_FF04, CHAR_KEY_ID, CHAR_KEY_NAME,
    CHAR_FF07, CHAR_BATTERY, CHAR_FF09, CHAR_FF0A, CHAR_FFF2,
    CHAR_MODEL, CHAR_SERIAL, CHAR_FIRMWARE, CHAR_HARDWARE,
    CHAR_SOFTWARE, CHAR_MANUFACTURER,
    DEVICE_PREFIXES, DEFAULT_SYSCODE, DEFAULT_REGCODE, Command,
)

from .models import (
    KeyInfo, ScannedKey, KeyType, KeyHardwareType, EventInfo, EventType
)

from .crypto import (
    aes_encrypt, aes_decrypt, crc16, xor_checksum,
    build_packet, parse_packet, is_crypto_available,
    derive_session_key, derive_session_key_v2,
)


class RayonicsSDK:
    """
    Rayonics BLE Smart Key SDK
    
    Supports two key hardware types:
    1. LSD4BT (newer) - Direct characteristic reads (ff03-ff0a)
    2. Encrypted (older B03009) - Requires encrypted protocol (ff01/ff02)
    
    Usage:
        sdk = RayonicsSDK()
        
        # Scan for keys
        keys = await sdk.scan()
        
        # Connect and read
        await sdk.connect(keys[0].device)
        info = await sdk.read_key_info()
        print(info)
        
        await sdk.disconnect()
    
    Or use context manager:
        async with RayonicsSDK() as sdk:
            keys = await sdk.scan()
            await sdk.connect(keys[0].device)
            info = await sdk.read_key_info()
    """
    
    def __init__(self, syscode: bytes = None, regcode: bytes = None):
        """
        Initialize SDK
        
        Args:
            syscode: System code for authentication (default: "6666")
            regcode: Registration code for authentication (default: "1111")
        """
        self._client: Optional[BleakClient] = None
        self._device: Optional[BLEDevice] = None
        self._syscode = syscode or DEFAULT_SYSCODE
        self._regcode = regcode or DEFAULT_REGCODE
        self._hardware_type = KeyHardwareType.UNKNOWN
        self._response = bytearray()
        self._response_event = asyncio.Event()
        self._authenticated = False
        self._session_key: Optional[bytes] = None  # Derived after CONNECT
        self._session_seed: Optional[bytes] = None  # 12-byte seed from CONNECT response
        self._connect_nonce: Optional[bytes] = None  # 10-byte nonce we sent
        self._connect_suffix: Optional[bytes] = None  # 2-byte suffix we sent
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()
    
    # ─────────────────────────────────────────────────────────────────────────
    # PROPERTIES
    # ─────────────────────────────────────────────────────────────────────────
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to a key"""
        return self._client is not None and self._client.is_connected
    
    @property
    def hardware_type(self) -> KeyHardwareType:
        """Get detected hardware type"""
        return self._hardware_type
    
    @property
    def is_authenticated(self) -> bool:
        """Check if authenticated (encrypted keys only)"""
        return self._authenticated
    
    @property
    def session_key(self) -> Optional[bytes]:
        """
        Get the derived session key (for debugging)
        
        This is derived from the CONNECT response and used for
        all subsequent encrypted commands.
        """
        return self._session_key
    
    # ─────────────────────────────────────────────────────────────────────────
    # CONFIGURATION
    # ─────────────────────────────────────────────────────────────────────────
    
    def set_codes(self, syscode: bytes, regcode: bytes):
        """
        Set authentication codes for encrypted protocol
        
        Args:
            syscode: 4-byte system code
            regcode: 4-byte registration code
        """
        self._syscode = syscode
        self._regcode = regcode
        self._authenticated = False
    
    def set_codes_from_strings(self, syscode: str, regcode: str):
        """
        Set codes from string format (as returned by eLOQ API)
        
        Args:
            syscode: Hex string like "11111bfb"
            regcode: Hex string like "11111bfb"
        """
        self._syscode = bytes.fromhex(syscode)
        self._regcode = bytes.fromhex(regcode)
        self._authenticated = False
    
    # ─────────────────────────────────────────────────────────────────────────
    # SCANNING
    # ─────────────────────────────────────────────────────────────────────────
    
    @staticmethod
    async def scan(timeout: float = 5.0, callback=None) -> List[ScannedKey]:
        """
        Scan for Rayonics BLE keys
        
        Args:
            timeout: Scan duration in seconds
            callback: Optional function called for each discovered key
                      callback(key: ScannedKey)
        
        Returns:
            List of discovered keys
        """
        found: List[ScannedKey] = []
        seen: set = set()
        
        def detection_callback(device: BLEDevice, adv_data):
            if device.address in seen:
                return
            
            name = device.name or adv_data.local_name or ""
            if not any(name.startswith(p) for p in DEVICE_PREFIXES):
                return
            
            seen.add(device.address)
            key = ScannedKey(
                device=device,
                name=name,
                address=device.address,
                rssi=adv_data.rssi or -100
            )
            found.append(key)
            
            if callback:
                callback(key)
        
        scanner = BleakScanner(detection_callback=detection_callback)
        await scanner.start()
        await asyncio.sleep(timeout)
        await scanner.stop()
        
        return found
    
    # ─────────────────────────────────────────────────────────────────────────
    # CONNECTION
    # ─────────────────────────────────────────────────────────────────────────
    
    async def connect(self, device: BLEDevice) -> bool:
        """
        Connect to a key
        
        Args:
            device: BLEDevice from scanning
        
        Returns:
            True if connected successfully
        """
        try:
            self._client = BleakClient(device)
            await self._client.connect()
            self._device = device
            self._authenticated = False
            
            # Detect hardware type by checking for ff03 readable characteristic
            self._hardware_type = KeyHardwareType.ENCRYPTED
            for service in self._client.services:
                for char in service.characteristics:
                    if char.uuid.lower() == CHAR_KEY_TYPE.lower():
                        if 'read' in char.properties:
                            self._hardware_type = KeyHardwareType.LSD4BT
                            break
            
            return True
            
        except Exception as e:
            self._client = None
            self._device = None
            raise ConnectionError(f"Failed to connect: {e}")
    
    async def disconnect(self):
        """Disconnect from key"""
        if self._client and self._client.is_connected:
            await self._client.disconnect()
        self._client = None
        self._device = None
        self._authenticated = False
        self._session_key = None
    
    # ─────────────────────────────────────────────────────────────────────────
    # READING - COMMON
    # ─────────────────────────────────────────────────────────────────────────
    
    async def read_key_info(self) -> KeyInfo:
        """
        Read all information from connected key
        
        Returns:
            KeyInfo object with all available data
        
        Raises:
            RuntimeError: If not connected
        """
        if not self.is_connected:
            raise RuntimeError("Not connected to a key")
        
        info = KeyInfo()
        info.hardware_type = self._hardware_type
        info.mac_address = self._device.address if self._device else ""
        
        if self._hardware_type == KeyHardwareType.LSD4BT:
            await self._read_lsd4bt(info)
        else:
            await self._read_encrypted(info)
        
        return info
    
    async def _read_char(self, uuid: str) -> Optional[bytes]:
        """Safely read a characteristic"""
        try:
            return await self._client.read_gatt_char(uuid)
        except:
            return None
    
    async def _read_char_str(self, uuid: str) -> str:
        """Read characteristic as string"""
        data = await self._read_char(uuid)
        if not data:
            return ""
        try:
            return data.decode('ascii').rstrip('\x00')
        except:
            return data.hex()
    
    # ─────────────────────────────────────────────────────────────────────────
    # READING - LSD4BT (Direct Characteristics)
    # ─────────────────────────────────────────────────────────────────────────
    
    async def _read_lsd4bt(self, info: KeyInfo):
        """Read from LSD4BT key using direct characteristics"""
        
        # Device info service
        info.model = await self._read_char_str(CHAR_MODEL)
        info.firmware = await self._read_char_str(CHAR_FIRMWARE)
        info.software = await self._read_char_str(CHAR_SOFTWARE)
        info.hardware = await self._read_char_str(CHAR_HARDWARE)
        info.serial = await self._read_char_str(CHAR_SERIAL)
        info.manufacturer = await self._read_char_str(CHAR_MANUFACTURER)
        
        # ff03 - Key type
        data = await self._read_char(CHAR_KEY_TYPE)
        if data:
            info.key_type = data[0]
            try:
                info.key_type_name = KeyType(data[0]).name
            except ValueError:
                info.key_type_name = f"UNKNOWN(0x{data[0]:02X})"
        
        # ff05 - Key ID
        info.key_id = await self._read_char_str(CHAR_KEY_ID)
        
        # ff06 - Key name
        info.name = await self._read_char_str(CHAR_KEY_NAME)
        
        # ff08 - Battery
        data = await self._read_char(CHAR_BATTERY)
        if data and len(data) >= 1:
            info.battery_percent = data[0]
        
        # Additional characteristics (for debugging/analysis)
        data = await self._read_char(CHAR_FF04)
        if data:
            info.ff04 = data.hex()
        
        data = await self._read_char(CHAR_FF07)
        if data:
            info.ff07 = data.hex()
            if len(data) >= 1:
                info.status_flag = data[0]
                # Bit 0 appears to indicate registration status
                info.is_registered = bool(data[0] & 0x01)
        
        data = await self._read_char(CHAR_FF09)
        if data:
            info.ff09 = data.hex()
            
        data = await self._read_char(CHAR_FF0A)
        if data:
            info.ff0a = data.hex()
            
        data = await self._read_char(CHAR_FFF2)
        if data:
            info.fff2 = data.hex()
    
    # ─────────────────────────────────────────────────────────────────────────
    # READING - ENCRYPTED (Older Keys)
    # ─────────────────────────────────────────────────────────────────────────
    
    async def _read_encrypted(self, info: KeyInfo):
        """Read from older key using encrypted protocol"""
        
        info.name = self._device.name if self._device else ""
        info.key_type_name = "ENCRYPTED (requires authentication)"
        
        if not is_crypto_available():
            raise RuntimeError(
                "PyCryptodome required for encrypted keys. "
                "Install with: pip install pycryptodome"
            )
        
        # Authenticate first
        if not self._authenticated:
            await self.authenticate()
    
    async def authenticate(self, try_defaults: bool = True) -> bool:
        """
        Authenticate with the key using syscode/regcode
        
        This sends CONNECT (0x0D) command and derives a session key from
        the response. The session key is then used for all subsequent
        encrypted commands.
        
        Args:
            try_defaults: If True, retry with default codes on failure
        
        Returns:
            True if authenticated successfully
        """
        if not is_crypto_available():
            raise RuntimeError("PyCryptodome required for authentication")
        
        # Subscribe to notifications
        await self._client.start_notify(NOTIFY_CHAR, self._on_notify)
        await asyncio.sleep(0.1)  # Give time for subscription
        
        # Try with configured codes first
        success = await self._try_connect(self._syscode, self._regcode)
        
        if not success and try_defaults:
            # Retry with default codes ("6666"/"1111")
            if self._syscode != DEFAULT_SYSCODE or self._regcode != DEFAULT_REGCODE:
                success = await self._try_connect(DEFAULT_SYSCODE, DEFAULT_REGCODE)
        
        return success
    
    async def _try_connect(self, syscode: bytes, regcode: bytes) -> bool:
        """
        Attempt CONNECT with specified codes
        
        The CONNECT packet contains a random nonce, NOT the codes!
        Codes are used CLIENT-SIDE to derive the session key from the response.
        
        Protocol:
        1. Client sends: 10-char random ASCII nonce + 2 random bytes
        2. Key responds: 12-byte session seed (static per key)
        3. Client derives session key from: nonce + seed + syscode + regcode
        
        Args:
            syscode: 4-byte system code (used for session key derivation)
            regcode: 4-byte registration code (used for session key derivation)
        
        Returns:
            True if successful, sets self._session_key and self._nonce
        """
        import random
        import string
        
        # Generate random 10-char ASCII alphanumeric nonce (like SDK does)
        nonce_ascii = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
        nonce = nonce_ascii.encode('ascii')
        
        # CRITICAL: Suffix must be CRC16 of nonce (not random!)
        # This was the key discovery - random suffix gets short error response,
        # CRC suffix gets full 15-byte response with seed
        from .crypto import crc16
        crc = crc16(nonce)
        suffix = bytes([crc & 0xFF, (crc >> 8) & 0xFF])  # Little-endian
        
        # Payload is nonce + CRC suffix (12 bytes total)
        payload = nonce + suffix
        
        # Store nonce for session key derivation
        self._connect_nonce = nonce
        self._connect_suffix = suffix
        
        # Use system key (RAYONICSBLEKEYV2) for initial CONNECT
        packet = build_packet(Command.CONNECT_AUTH, payload)
        
        # Send and wait for response
        self._response.clear()
        self._response_event.clear()
        
        await self._client.write_gatt_char(WRITE_CHAR, packet, response=False)
        
        try:
            await asyncio.wait_for(self._response_event.wait(), timeout=3.0)
            
            if len(self._response) >= 19:
                # Parse with system key
                cmd, resp_payload, valid, raw_decrypted = parse_packet(bytes(self._response))
                
                if valid and cmd == Command.CONNECT_AUTH:
                    # Check response length
                    resp_length = raw_decrypted[0]
                    
                    if resp_length == 15:
                        # Success! Got full session seed
                        session_seed = raw_decrypted[2:14]
                        
                        # Derive session key from nonce + seed + codes
                        # Key = nonce^seed (10) + syscode (4) + CRC16(first14) (2)
                        self._session_key = derive_session_key_v2(
                            nonce, suffix, session_seed, syscode, regcode
                        )
                        self._session_seed = session_seed
                        
                        # Now send verifyCode (0x0F) with regcode + syscode + flags
                        # This completes the authentication handshake
                        verify_success = await self._send_verify_code(regcode, syscode)
                        
                        if verify_success:
                            self._authenticated = True
                            return True
                        else:
                            # verifyCode failed - wrong codes?
                            self._session_key = None
                            return False
                    elif resp_length == 4:
                        # Error response
                        error_code = raw_decrypted[2]
                        # Error 0x01 = auth failed / session locked / etc.
                        return False
                    
        except asyncio.TimeoutError:
            pass
        
        return False
    
    def _on_notify(self, sender, data: bytearray):
        """Handle notification from key"""
        self._response.extend(data)
        self._response_event.set()
    
    async def _send_verify_code(self, regcode: bytes, syscode: bytes) -> bool:
        """
        Send verifyCode (0x0F) command after CONNECT
        
        This completes the authentication handshake. The payload is:
        regcode (4 bytes) + syscode (4 bytes) + flags (1 byte)
        
        Captured traffic shows flags = 0x04 (purpose unclear, maybe permission level)
        
        Args:
            regcode: 4-byte registration code
            syscode: 4-byte system code
        
        Returns:
            True if verification succeeded
        """
        if not self._session_key:
            return False
        
        # Build verifyCode payload: regcode + syscode + flags
        flags = 0x04  # From captured traffic
        payload = regcode[:4] + syscode[:4] + bytes([flags])
        
        # Build encrypted packet with session key (frame=2)
        packet = build_packet(Command.VERIFY_CODE, payload, key=self._session_key)
        
        # Send and wait for response
        self._response.clear()
        self._response_event.clear()
        
        await self._client.write_gatt_char(WRITE_CHAR, packet, response=False)
        
        try:
            await asyncio.wait_for(self._response_event.wait(), timeout=3.0)
            
            if len(self._response) >= 19:
                # Parse with session key
                cmd, resp_payload, valid, raw_decrypted = parse_packet(
                    bytes(self._response), key=self._session_key
                )
                
                if valid and cmd == Command.VERIFY_CODE:
                    # Check for success (response payload starts with 0x00 = success)
                    if raw_decrypted[2] == 0x00:
                        return True
                    
        except asyncio.TimeoutError:
            pass
        
        return False
    
    # ─────────────────────────────────────────────────────────────────────────
    # COMMANDS
    # ─────────────────────────────────────────────────────────────────────────
    
    async def send_command(self, cmd: int, payload: bytes = b"", timeout: float = 2.0) -> Optional[bytes]:
        """
        Send a command and wait for response
        
        Uses session key if authenticated, otherwise uses system key.
        
        Args:
            cmd: Command code
            payload: Command data
            timeout: Response timeout in seconds
        
        Returns:
            Response payload or None on timeout
        """
        if not self.is_connected:
            raise RuntimeError("Not connected")
        
        if not is_crypto_available():
            raise RuntimeError("PyCryptodome required")
        
        # Ensure notifications are subscribed
        try:
            await self._client.start_notify(NOTIFY_CHAR, self._on_notify)
        except:
            pass  # Already subscribed
        
        # Use session key if available, otherwise system key
        key = self._session_key if self._authenticated else None
        packet = build_packet(cmd, payload, key=key)
        
        self._response.clear()
        self._response_event.clear()
        
        await self._client.write_gatt_char(WRITE_CHAR, packet, response=False)
        
        try:
            await asyncio.wait_for(self._response_event.wait(), timeout=timeout)
            
            if len(self._response) >= 19:
                # Parse with same key used for sending
                resp_cmd, resp_payload, valid, _ = parse_packet(bytes(self._response), key=key)
                if valid:
                    return resp_payload
        except asyncio.TimeoutError:
            pass
        
        return None
    
    async def get_key_info_raw(self) -> Optional[dict]:
        """
        Get key info (0x11) - returns raw parsed data
        
        Returns:
            Dict with keyId, keyType, groupId, verifyDay, isBleOnline, power
        """
        resp = await self.send_command(Command.GET_KEY_INFO)
        if resp and len(resp) >= 10:
            return {
                "keyId": resp[0] | (resp[1] << 8),
                "keyType": resp[2],
                "groupId": resp[3] | (resp[4] << 8),
                "verifyDay": resp[6] | (resp[7] << 8),
                "isBleOnline": resp[8],
                "power": resp[9]
            }
        return None
    
    async def get_version(self) -> str:
        """
        Get key version string (0x34)
        
        Returns:
            Version string like "B03009V301"
        """
        resp = await self.send_command(0x34)  # GET_KEY_VERSION
        if resp:
            # Decode ASCII, stop at null or non-printable
            version = ""
            for b in resp:
                if b == 0 or b > 127:
                    break
                version += chr(b)
            return version
        return ""
    
    async def get_event_count(self) -> int:
        """
        Get number of events stored in key
        
        Returns:
            Event count or 0 on error
        """
        resp = await self.send_command(Command.GET_EVENT_COUNT)
        if resp and len(resp) >= 2:
            return resp[0] | (resp[1] << 8)
        return 0
    
    async def get_event(self, position: int) -> Optional[dict]:
        """
        Get event at position (1-based index)
        
        Event structure (from reverse engineering):
        - bytes 0-1: keyId (uint16 LE)
        - byte 2: unknown
        - bytes 3-4: lockId (uint16 LE)
        - bytes 5-10: timestamp (BCD: YY MM DD HH MM SS)
        - byte 11: event type
        
        Args:
            position: Event index (1-based, like Android SDK)
        
        Returns:
            Dict with time, lockId, keyId, event or None
        """
        payload = bytes([position & 0xFF, (position >> 8) & 0xFF])
        resp = await self.send_command(Command.GET_EVENT, payload)
        
        if resp and len(resp) >= 12:
            # BCD decoder
            def bcd(b): return ((b >> 4) * 10) + (b & 0x0F)
            
            key_id = resp[0] | (resp[1] << 8)
            lock_id = resp[3] | (resp[4] << 8)
            
            # BCD timestamp
            year = 2000 + bcd(resp[5])
            month = bcd(resp[6])
            day = bcd(resp[7])
            hour = bcd(resp[8])
            minute = bcd(resp[9])
            second = bcd(resp[10])
            
            event_type = resp[11]
            
            return {
                "time": f"{year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}",
                "lockId": lock_id,
                "keyId": key_id,
                "event": event_type
            }
        
        return None
    
    async def get_all_events(self, clear_after: bool = False) -> List[dict]:
        """
        Read all events from key
        
        Args:
            clear_after: If True, clear events from key after reading (like iOS/Android apps)
        
        Returns:
            List of event dicts with time, lockId, keyId, event
        """
        count = await self.get_event_count()
        events = []
        
        for i in range(1, count + 1):  # 1-based indexing
            event = await self.get_event(i)
            if event:
                events.append(event)
            await asyncio.sleep(0.15)  # Small delay between reads
        
        # Clear events if requested (like iOS/Android SDKs do)
        if clear_after and events:
            await self.clear_events()
        
        return events
    
    async def clear_events(self) -> bool:
        """
        Clear all events from key (CLEAN_EVENT 0x28)
        
        This is what iOS/Android apps do after reading events.
        
        Returns:
            True if successful
        """
        resp = await self.send_command(Command.CLEAN_EVENT)
        return resp is not None
    
    async def read_all(self) -> dict:
        """
        Read all available information from the key
        
        Returns JSON-compatible dict matching Android SDK format:
        {
            "device": "B03009...",
            "mac": "...",
            "keyInfo": { keyId, keyType, groupId, verifyDay, power },
            "version": "B03009V301",
            "events": { count, eventList: [...] }
        }
        """
        if not self._authenticated:
            await self.authenticate()
        
        result = {
            "device": self._device.name if self._device else "",
            "mac": self._device.address if self._device else ""
        }
        
        # Key info
        key_info = await self.get_key_info_raw()
        if key_info:
            result["keyInfo"] = {
                "keyId": key_info["keyId"],
                "keyType": key_info["keyType"],
                "groupId": key_info["groupId"],
                "verifyDay": key_info["verifyDay"],
                "isBleOnline": key_info["isBleOnline"],
                "power": f"{key_info['power']}%"
            }
        
        # Version
        result["version"] = await self.get_version()
        
        # Events
        event_count = await self.get_event_count()
        events = await self.get_all_events()
        result["events"] = {
            "count": event_count,
            "eventList": events
        }
        
        return result


# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

async def scan_keys(timeout: float = 5.0, callback=None) -> List[ScannedKey]:
    """
    Scan for Rayonics keys
    
    Args:
        timeout: Scan duration in seconds
        callback: Optional function called for each discovered key
    
    Returns:
        List of discovered keys
    """
    return await RayonicsSDK.scan(timeout, callback)


async def read_key(
    device: BLEDevice,
    syscode: bytes = None,
    regcode: bytes = None
) -> Optional[KeyInfo]:
    """
    Connect, read, and disconnect from a key
    
    Args:
        device: BLEDevice from scanning
        syscode: Optional system code
        regcode: Optional registration code
    
    Returns:
        KeyInfo or None on error
    """
    async with RayonicsSDK(syscode, regcode) as sdk:
        await sdk.connect(device)
        return await sdk.read_key_info()
