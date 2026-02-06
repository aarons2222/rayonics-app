"""
Rayonics BLE Smart Key SDK
Cross-platform Python implementation (Windows/Mac/Linux)

Usage:
    from rayonics_ble import RayonicsSDK, scan_keys, read_key
    
    # Quick scan and read
    keys = await scan_keys()
    info = await read_key(keys[0].device)
    
    # Or use the SDK class directly
    sdk = RayonicsSDK()
    keys = await sdk.scan()
    await sdk.connect(keys[0].device)
    info = await sdk.read_key()
    await sdk.disconnect()
"""

from .sdk import (
    RayonicsSDK,
    scan_keys,
    read_key,
)

from .models import (
    KeyInfo,
    ScannedKey,
    KeyType,
    KeyHardwareType,
    EventType,
    EventInfo,
)

from .constants import (
    SERVICE_UUID,
    WRITE_CHAR,
    NOTIFY_CHAR,
    DEVICE_PREFIXES,
    AES_KEY,
    DEFAULT_SYSCODE,
    DEFAULT_REGCODE,
)

from .crypto import (
    aes_encrypt,
    aes_decrypt,
    crc16,
    xor_checksum,
    build_packet,
    parse_packet,
    is_crypto_available,
)

__version__ = "1.0.0"
__all__ = [
    # Main SDK
    "RayonicsSDK",
    "scan_keys",
    "read_key",
    # Models
    "KeyInfo",
    "ScannedKey",
    "KeyType",
    "KeyHardwareType",
    "EventType",
    "EventInfo",
    # Constants
    "SERVICE_UUID",
    "WRITE_CHAR",
    "NOTIFY_CHAR",
    "DEVICE_PREFIXES",
    "AES_KEY",
    "DEFAULT_SYSCODE",
    "DEFAULT_REGCODE",
    # Crypto
    "aes_encrypt",
    "aes_decrypt",
    "crc16",
    "xor_checksum",
    "build_packet",
    "parse_packet",
    "is_crypto_available",
]
