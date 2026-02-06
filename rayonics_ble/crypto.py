"""
Rayonics BLE SDK - Cryptography Functions
"""

from .constants import AES_KEY

try:
    from Crypto.Cipher import AES
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


def crc16(data: bytes) -> int:
    """
    CRC16-KERMIT checksum (polynomial 0x8408, init 0xFFFF, final XOR 0xFFFF)
    
    Used for packet integrity verification.
    Returns as little-endian integer ready to split into [low byte][high byte]
    """
    crc = 0xFFFF
    for byte in data:
        crc ^= byte & 0xFF
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0x8408
            else:
                crc >>= 1
    crc ^= 0xFFFF  # Final XOR
    return crc & 0xFFFF


def xor_checksum(data: bytes) -> int:
    """
    XOR checksum of all bytes
    
    Used inside encrypted payload for integrity.
    """
    result = 0
    for b in data:
        result ^= b
    return result


def aes_encrypt(data: bytes, key: bytes = None) -> bytes:
    """
    AES-128-ECB encrypt
    
    Args:
        data: Plaintext to encrypt (will be padded to 16 bytes)
        key: AES key (defaults to RAYONICSBLEKEYV2)
    
    Returns:
        16 bytes of ciphertext
    
    Raises:
        RuntimeError: If pycryptodome not installed
    """
    if not HAS_CRYPTO:
        raise RuntimeError(
            "PyCryptodome not installed. "
            "Install with: pip install pycryptodome"
        )
    
    key = key or AES_KEY
    cipher = AES.new(key, AES.MODE_ECB)
    
    # Pad to 16 bytes
    padded = (data + b'\x00' * 16)[:16]
    return cipher.encrypt(padded)


def aes_decrypt(data: bytes, key: bytes = None) -> bytes:
    """
    AES-128-ECB decrypt
    
    Args:
        data: Ciphertext (must be 16 bytes)
        key: AES key (defaults to RAYONICSBLEKEYV2)
    
    Returns:
        16 bytes of plaintext
    
    Raises:
        RuntimeError: If pycryptodome not installed
    """
    if not HAS_CRYPTO:
        raise RuntimeError(
            "PyCryptodome not installed. "
            "Install with: pip install pycryptodome"
        )
    
    key = key or AES_KEY
    cipher = AES.new(key, AES.MODE_ECB)
    return cipher.decrypt(data[:16])


def build_packet(cmd: int, payload: bytes = b"", key: bytes = None, frame: int = None) -> bytes:
    """
    Build a 19-byte encrypted packet
    
    Format: [frame(1)] + [AES encrypted(16)] + [CRC16(2)]
    
    Inner plaintext structure (16 bytes total):
        [length(1)][cmd(1)][payload(N)][xor(1)][padding][0x00]
        
        - length: data_len + 3 (for most commands) or data_len + 2 (for VERIFY)
        - cmd: command code
        - payload: command data (variable length)
        - xor: XOR checksum at position (payload_len + 2)
        - padding: zeros to fill 16 bytes
    
    Args:
        cmd: Command code
        payload: Command data (max 12 bytes)
        key: Encryption key (defaults to RAYONICSBLEKEYV2)
             Use session key for commands after CONNECT
        frame: Frame byte (auto-detected if None):
               0x01 = system key (RAYONICSBLEKEYV2)
               0x02 = session key (after authentication)
    
    Returns:
        19-byte packet ready to send
    """
    # Auto-detect frame based on key
    if frame is None:
        frame = 0x02 if key is not None else 0x01
    
    # Length formula from native libbleKey.so:
    # - Native uses data_len + 3 for most commands
    # - VERIFY (9 bytes payload) uses data_len + 2 empirically
    if len(payload) == 9:  # Special case for VERIFY command
        length = len(payload) + 2
    else:
        length = len(payload) + 3
    
    # Build the data portion: [length][cmd][payload]
    data = bytes([length, cmd]) + payload
    
    # XOR checksum position = payload_len + 2 (right after length + cmd + payload)
    xor_pos = len(payload) + 2
    xor = xor_checksum(data)
    
    # Build 16-byte plaintext: data + xor at position + zeros
    plaintext = bytearray(16)
    plaintext[:len(data)] = data
    plaintext[xor_pos] = xor
    plaintext = bytes(plaintext)
    
    # Encrypt with specified key
    encrypted = aes_encrypt(plaintext, key=key)
    
    # Add frame + CRC
    frame_enc = bytes([frame]) + encrypted
    crc = crc16(frame_enc)
    
    return frame_enc + bytes([crc & 0xFF, crc >> 8])


def parse_packet(data: bytes, key: bytes = None) -> tuple:
    """
    Parse a 19-byte response packet
    
    Args:
        data: Raw 19-byte packet
        key: Decryption key (defaults to RAYONICSBLEKEYV2)
             Use session key for responses after CONNECT
    
    Returns:
        (cmd, payload, valid, raw_decrypted) tuple
        - cmd: Command code from response
        - payload: Decrypted payload bytes (data portion)
        - valid: True if CRC and XOR checksums pass
        - raw_decrypted: Full 16-byte decrypted data (for session key derivation)
    """
    if len(data) != 19:
        return (0, b"", False, b"")
    
    # Check CRC (little-endian)
    frame_enc = data[:17]
    crc_recv = data[17] | (data[18] << 8)
    crc_calc = crc16(frame_enc)
    
    if crc_recv != crc_calc:
        return (0, b"", False, b"")
    
    # Decrypt
    encrypted = data[1:17]
    plaintext = aes_decrypt(encrypted, key=key)
    
    # Parse inner structure: [length][cmd][data...][xor][0x00]
    length = plaintext[0]
    cmd = plaintext[1]
    
    # Safety check for malformed responses
    if length < 3 or length > 15:
        return (cmd, plaintext[2:14], False, plaintext)
    
    # Payload is bytes 2 through (length-2), since length includes len+cmd+xor
    # For length=15: data is bytes 2-13 (12 bytes)
    # For length=4: data is byte 2 only (1 byte)
    payload_end = min(length - 1, 14)  # Don't go past byte 13
    payload = plaintext[2:payload_end]
    
    # XOR is at position 14
    xor_recv = plaintext[14]
    
    # Verify XOR of bytes 0-13
    xor_calc = xor_checksum(plaintext[:14])
    valid = (xor_recv == xor_calc)
    
    return (cmd, payload, valid, plaintext)


def is_crypto_available() -> bool:
    """Check if encryption is available"""
    return HAS_CRYPTO


def derive_session_key(response: bytes) -> bytes:
    """
    Derive session key from CONNECT response (legacy method)
    
    The official SDK derives a "transpose key" (trancKey) from the
    decrypted CONNECT response using XOR:
    
        trancKey[i] = response[i] XOR response[i+10]
    
    This session key is then used for ALL subsequent commands instead
    of the static RAYONICSBLEKEYV2 key.
    
    Args:
        response: 16-byte decrypted response from CONNECT command
    
    Returns:
        16-byte session key
    """
    # Ensure we have at least 16 bytes
    if len(response) < 16:
        response = (response + b'\x00' * 16)[:16]
    
    session_key = bytearray(16)
    
    # XOR first 10 bytes with bytes at offset +10
    # This creates a 10-byte "transpose" pattern
    for i in range(10):
        idx2 = i + 10 if i + 10 < len(response) else i
        session_key[i] = response[i] ^ response[idx2]
    
    # Remaining bytes (indices 10-15)
    # Based on disassembly, these may be zeros or continue the XOR pattern
    for i in range(10, 16):
        session_key[i] = 0
    
    return bytes(session_key)


def derive_session_key_v2(
    nonce: bytes,
    suffix: bytes, 
    seed: bytes,
    syscode: bytes,
    regcode: bytes
) -> bytes:
    """
    Derive session key from CONNECT nonce, response seed, and codes.
    
    CORRECT ALGORITHM (from Android libbleKey.so KeyPack::createTransposeKey):
    
    The session key is 16 bytes:
    - Bytes 0-9:   nonce[0:10] XOR seed[0:10]
    - Bytes 10-13: syscode[0:4]
    - Bytes 14-15: CRC16(key[0:14])  <- This was the missing piece!
    
    The CRC is CRC16-KERMIT (poly=0x8408, init=0xFFFF, xor_out=0xFFFF).
    
    After CONNECT, the verifyCode command (0x0F) sends regcode+syscode+flags.
    
    Args:
        nonce: 10-byte random ASCII nonce we sent
        suffix: 2-byte CRC suffix we sent (not used in derivation)
        seed: 12-byte session seed from key response (first 10 bytes used)
        syscode: 4-byte system code
        regcode: 4-byte registration code (used in verifyCode, not derivation)
    
    Returns:
        16-byte session key for subsequent encrypted commands
    """
    session_key = bytearray(16)
    
    # Bytes 0-9: nonce XOR seed (first 10 bytes of each)
    for i in range(10):
        session_key[i] = nonce[i] ^ seed[i]
    
    # Bytes 10-13: syscode (4 bytes)
    session_key[10:14] = syscode[:4]
    
    # Bytes 14-15: CRC16-KERMIT of first 14 bytes (little-endian)
    crc = crc16(bytes(session_key[:14]))
    session_key[14] = crc & 0xFF         # Low byte
    session_key[15] = (crc >> 8) & 0xFF  # High byte
    
    return bytes(session_key)
