"""
Rayonics BLE SDK - Constants and Protocol Values
"""

# ═══════════════════════════════════════════════════════════════════════════════
# BLE UUIDs
# ═══════════════════════════════════════════════════════════════════════════════

SERVICE_UUID = "0000ff12-0000-1000-8000-00805f9b34fb"
WRITE_CHAR = "0000ff01-0000-1000-8000-00805f9b34fb"
NOTIFY_CHAR = "0000ff02-0000-1000-8000-00805f9b34fb"

# Direct-read characteristics (LSD4BT keys)
CHAR_KEY_TYPE = "0000ff03-0000-1000-8000-00805f9b34fb"
CHAR_FF04 = "0000ff04-0000-1000-8000-00805f9b34fb"
CHAR_KEY_ID = "0000ff05-0000-1000-8000-00805f9b34fb"
CHAR_KEY_NAME = "0000ff06-0000-1000-8000-00805f9b34fb"
CHAR_FF07 = "0000ff07-0000-1000-8000-00805f9b34fb"
CHAR_BATTERY = "0000ff08-0000-1000-8000-00805f9b34fb"
CHAR_FF09 = "0000ff09-0000-1000-8000-00805f9b34fb"
CHAR_FF0A = "0000ff0a-0000-1000-8000-00805f9b34fb"
CHAR_FFF2 = "0000fff2-0000-1000-8000-00805f9b34fb"

# Device Info Service characteristics
CHAR_MODEL = "00002a24-0000-1000-8000-00805f9b34fb"
CHAR_SERIAL = "00002a25-0000-1000-8000-00805f9b34fb"
CHAR_FIRMWARE = "00002a26-0000-1000-8000-00805f9b34fb"
CHAR_HARDWARE = "00002a27-0000-1000-8000-00805f9b34fb"
CHAR_SOFTWARE = "00002a28-0000-1000-8000-00805f9b34fb"
CHAR_MANUFACTURER = "00002a29-0000-1000-8000-00805f9b34fb"


# ═══════════════════════════════════════════════════════════════════════════════
# DEVICE IDENTIFICATION
# ═══════════════════════════════════════════════════════════════════════════════

DEVICE_PREFIXES = ["B03005", "B03009", "B03018", "RayonicsKEY", "LSD4BT"]


# ═══════════════════════════════════════════════════════════════════════════════
# ENCRYPTION
# ═══════════════════════════════════════════════════════════════════════════════

AES_KEY = b"RAYONICSBLEKEYV2"

# Default codes (from Android SDK KeyBasicInfo.java)
DEFAULT_SYSCODE = bytes([0x36, 0x36, 0x36, 0x36])  # "6666"
DEFAULT_REGCODE = bytes([0x31, 0x31, 0x31, 0x31])  # "1111"


# ═══════════════════════════════════════════════════════════════════════════════
# COMMANDS (from KeyPack.cpp)
# ═══════════════════════════════════════════════════════════════════════════════

class Command:
    """Protocol command codes"""
    WRITE_INFO = 0x01          # Write key info
    READ_INFO = 0x02           # Read key info
    OPEN_LOCK = 0x03           # Open lock command
    READ_LOCK_INFO = 0x04      # Read lock info
    SET_KEY_SETTING = 0x05     # Configure setting key
    READ_KEY_SETTING = 0x06    # Read setting key config
    KEY_READY = 0x07           # Key ready signal
    UNLOCK = 0x08              # Unlock
    LOCK = 0x09                # Lock
    READ_BLACKLIST = 0x0B      # Read blacklist
    WRITE_BLACKLIST = 0x0C     # Write blacklist
    CONNECT_AUTH = 0x0D        # Connection authentication
    SET_CONNECT_KEY = 0x0E     # Set connect key (after connect)
    VERIFY_CODE = 0x0F         # Verify code (regcode + syscode + flags)
    GET_LOCK_ANGLE = 0x10      # Get lock angle (from iOS SDK)
    GET_KEY_INFO = 0x11        # Get key information (keyId, type, group, etc)
    RESET_KEY = 0x12           # Reset key
    SET_ENGINEER_KEY = 0x13    # Set engineer key
    SET_EMERGENCY_KEY = 0x14   # Set emergency key
    SET_USER_KEY = 0x15        # Set user key
    SET_BLACKLIST_KEY = 0x16   # Set blacklist key
    CLEAR_OPEN_RECORD = 0x18   # Clear open records
    GET_SEQUENCE_OPEN = 0x19   # Get sequence open info
    READ_TRACE = 0x1A          # Read trace info
    WRITE_TRACE = 0x1B         # Write trace info
    GET_EVENT_COUNT = 0x26     # Get event count
    GET_EVENT = 0x27           # Get event by position
    CLEAN_EVENT = 0x28         # Clean all events
    GET_KEY_VERSION = 0x34     # Get key version string (e.g. "B03009V301")
    SET_KEY_TIME = 0x60        # Set key time
