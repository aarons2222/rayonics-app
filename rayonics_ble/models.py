"""
Rayonics BLE SDK - Data Models
"""

from enum import IntEnum
from dataclasses import dataclass
from typing import Optional
from bleak.backends.device import BLEDevice


# ═══════════════════════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════════════════════

class KeyHardwareType(IntEnum):
    """Hardware type detection"""
    UNKNOWN = 0
    LSD4BT = 1      # Newer model with direct characteristic reads
    ENCRYPTED = 2   # Older model requiring encrypted protocol


class KeyType(IntEnum):
    """
    Key function types (from Android SDK)
    
    Each key has a specific purpose in the eLOQ system:
    - USER: Normal user access key
    - SETTING: System configuration key
    - AUDIT: Audit trail key
    - BLACKLIST: For blocking keys
    - etc.
    """
    BLANK = 0x00
    USER = 0x50           # Normal user key
    SETTING = 0x12        # Setting/admin key
    REGISTER = 0x11       # Registration key
    AUDIT = 0x13          # Audit key
    BLACKLIST = 0x15      # Blacklist key
    CONSTRUCTION = 0x25   # Construction key
    VERIFY = 0x20         # Verification key
    TRACE = 0x21          # Trace key
    EMERGENCY = 0xF6      # Emergency key
    AUXILIARY = 0x16      # Auxiliary key
    ADVANCED = 0x17       # Advanced key
    ELECTRICITY = 0xF5    # Electricity meter key
    LOGOUT = 0xF2         # Logout key
    LSD4BT = 0x06         # LSD4BT specific type


class EventType(IntEnum):
    """
    Event types stored in lock memory
    (from KeyEventType.java)
    """
    UNKNOWN = 0
    OPEN_SUCCESS = 1
    OPEN_FAIL = 2
    SET_SUCCESS = 3
    SET_FAIL = 4
    NO_PERMISSION = 5
    BLACKLISTED = 6
    TIME_EXPIRED = 7
    OUTSIDE_SCHEDULE = 8
    READ_AUDIT = 9
    READ_BLACKLIST = 10
    SEQUENCE_OPEN = 11
    SEQUENCE_CANCEL = 12
    EMERGENCY_OPEN = 13
    POWER_ON = 14
    LOW_BATTERY = 15
    TAMPER = 16
    LOCK_LOCKED = 17
    LOCK_UNLOCKED = 18


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ScannedKey:
    """A discovered key from BLE scanning"""
    device: BLEDevice
    name: str
    address: str
    rssi: int
    
    def __str__(self):
        return f"🔑 {self.name} [{self.address}] RSSI:{self.rssi}"


@dataclass
class KeyInfo:
    """Information read from a key"""
    
    # Basic info
    key_id: str = ""
    key_type: int = 0
    key_type_name: str = ""
    battery_percent: int = 0
    
    # Device info
    model: str = ""
    firmware: str = ""
    software: str = ""
    hardware: str = ""
    serial: str = ""
    manufacturer: str = ""
    
    # Key details
    name: str = ""
    mac_address: str = ""
    hardware_type: KeyHardwareType = KeyHardwareType.UNKNOWN
    
    # User key specific
    user_id: str = ""
    valid_start: Optional[str] = None
    valid_end: Optional[str] = None
    timezone_mask: int = 0
    
    # Parsed characteristic values
    status_flag: int = 0          # ff07 - status/state flag
    is_registered: bool = False   # derived from ff07
    
    # Raw characteristic values (for debugging)
    ff04: str = ""
    ff07: str = ""
    ff09: str = ""
    ff0a: str = ""
    fff2: str = ""
    
    def __str__(self):
        # Build battery indicator
        battery_bar = self._battery_bar()
        
        # Build key type description
        key_type_desc = self._key_type_description()
        
        lines = [
            "═" * 50,
            "🔑 KEY INFORMATION",
            "═" * 50,
            "",
            "📋 Identity",
            f"   Key ID       : {self.key_id or '(not set)'}",
            f"   Name         : {self.name or '(unnamed)'}",
            f"   MAC Address  : {self.mac_address}",
            "",
            "🔧 Type & Status",
            f"   Key Type     : {key_type_desc}",
            f"   Hardware     : {self.hardware_type.name}",
            f"   Registered   : {'Yes' if self.is_registered else 'No'}",
            f"   Battery      : {battery_bar}",
            "",
            "📱 Device Info",
            f"   Model        : {self.model or '(unknown)'}",
            f"   Firmware     : {self.firmware or '(unknown)'}",
            f"   Software     : {self.software or '(unknown)'}",
            f"   Manufacturer : {self.manufacturer or '(unknown)'}",
        ]
        
        # Add raw data section if present
        if any([self.ff04, self.ff07, self.ff09, self.ff0a, self.fff2]):
            lines.append("")
            lines.append("🔬 Raw Characteristics")
            if self.ff04:
                lines.append(f"   ff04: {self.ff04}")
            if self.ff07:
                lines.append(f"   ff07: {self.ff07} (status flag: {self.status_flag})")
            if self.ff09:
                lines.append(f"   ff09: {self.ff09}")
            if self.ff0a:
                lines.append(f"   ff0a: {self.ff0a}")
            if self.fff2:
                lines.append(f"   fff2: {self.fff2}")
        
        lines.append("")
        lines.append("═" * 50)
        return "\n".join(lines)
    
    def _battery_bar(self) -> str:
        """Generate a visual battery indicator"""
        pct = self.battery_percent
        filled = pct // 10
        empty = 10 - filled
        bar = "█" * filled + "░" * empty
        if pct > 50:
            return f"[{bar}] {pct}% ✓"
        elif pct > 20:
            return f"[{bar}] {pct}% ⚠️"
        else:
            return f"[{bar}] {pct}% ⚠️ LOW"
    
    def _key_type_description(self) -> str:
        """Get human-readable key type description"""
        descriptions = {
            0x00: "Blank (uninitialized)",
            0x06: "LSD4BT Hardware",
            0x11: "Registration Key (for registering locks)",
            0x12: "Setting Key (admin/config)",
            0x13: "Audit Key (read lock events)",
            0x15: "Blacklist Key (block users)",
            0x16: "Auxiliary Key",
            0x17: "Advanced Key",
            0x20: "Verify Key",
            0x21: "Trace Key",
            0x23: "Construction Key (temporary)",
            0x50: "User Key (standard access)",
            0xF2: "Logout Key",
            0xF5: "Electricity Key (power check)",
            0xF6: "Emergency Key (override)",
        }
        desc = descriptions.get(self.key_type, "Unknown")
        return f"0x{self.key_type:02X} - {desc}"
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "key_id": self.key_id,
            "key_type": self.key_type,
            "key_type_name": self.key_type_name,
            "key_type_description": self._key_type_description(),
            "battery_percent": self.battery_percent,
            "model": self.model,
            "firmware": self.firmware,
            "software": self.software,
            "hardware": self.hardware,
            "serial": self.serial,
            "manufacturer": self.manufacturer,
            "name": self.name,
            "mac_address": self.mac_address,
            "hardware_type": self.hardware_type.name,
            "is_registered": self.is_registered,
            "status_flag": self.status_flag,
            "raw": {
                "ff04": self.ff04,
                "ff07": self.ff07,
                "ff09": self.ff09,
                "ff0a": self.ff0a,
                "fff2": self.fff2,
            }
        }


@dataclass
class EventInfo:
    """Event record from lock"""
    
    event_type: EventType = EventType.UNKNOWN
    event_type_name: str = ""
    timestamp: Optional[str] = None
    key_id: str = ""
    lock_id: str = ""
    user_id: str = ""
    raw_data: bytes = b""
    
    def __str__(self):
        return f"[{self.timestamp}] {self.event_type_name} - Key:{self.key_id}"
    
    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "event_type_name": self.event_type_name,
            "timestamp": self.timestamp,
            "key_id": self.key_id,
            "lock_id": self.lock_id,
            "user_id": self.user_id,
        }


@dataclass
class LockInfo:
    """Lock information (from setting key)"""
    
    lock_id: str = ""
    lock_name: str = ""
    firmware: str = ""
    battery_percent: int = 0
    event_count: int = 0
    
    def __str__(self):
        return f"🔒 {self.lock_name} [{self.lock_id}] Battery:{self.battery_percent}%"
