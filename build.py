#!/usr/bin/env python3
"""
PyInstaller build script for Rayonics Key Reader.

Creates a single-file executable that bundles the Python server,
BLE handler, SDK, and static web assets.

Usage:
    python build.py
"""

import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
STATIC = ROOT / "static"
NAME = "RayonicsKeyReader"


def main():
    args = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", NAME,
        # Bundle static/ as data
        "--add-data", f"{STATIC}{':' if platform.system() != 'Windows' else ';'}static",
        # Bundle the SDK package
        "--add-data", f"{ROOT / 'rayonics_ble'}{':' if platform.system() != 'Windows' else ';'}rayonics_ble",
        # Hidden imports that PyInstaller may miss
        "--hidden-import", "bleak",
        "--hidden-import", "websockets",
        "--hidden-import", "Crypto",
        "--hidden-import", "Crypto.Cipher",
        "--hidden-import", "Crypto.Cipher.AES",
    ]

    # Hide console window on Windows
    if platform.system() == "Windows":
        args.append("--noconsole")

    # Entry point
    args.append(str(ROOT / "server.py"))

    print(f"Building {NAME}…")
    print(f"  Command: {' '.join(args)}\n")

    result = subprocess.run(args)
    if result.returncode == 0:
        dist = ROOT / "dist" / NAME
        if platform.system() == "Windows":
            dist = dist.with_suffix(".exe")
        print(f"\n✅ Build complete: {dist}")
    else:
        print(f"\n❌ Build failed (exit code {result.returncode})")
        sys.exit(result.returncode)


if __name__ == "__main__":
    main()
