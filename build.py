#!/usr/bin/env python3
"""
Build a standalone executable using PyInstaller.

Usage:
    python build.py          # GUI version (default)
    python build.py --cli    # Terminal/headless version
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
ASSETS = ROOT / "assets"

cli_mode = "--cli" in sys.argv
entry = "server.py" if cli_mode else "app.py"
name = "eLOQ Sync"

# Data separator differs per platform
sep = ";" if sys.platform == "win32" else ":"

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--onefile",
    "--name", name,
    f"--add-data=static{sep}static",
    f"--add-data=assets{sep}assets",
    "--hidden-import", "bleak",
    "--hidden-import", "aiohttp",
    entry,
]

# Platform-specific options
if not cli_mode:
    if sys.platform == "win32":
        cmd.append("--noconsole")
        ico = ASSETS / "icon.ico"
        if ico.exists():
            cmd.extend(["--icon", str(ico)])
    elif sys.platform == "darwin":
        cmd.append("--windowed")
        cmd.extend(["--osx-bundle-identifier", "com.eloq.sync"])
        icns = ASSETS / "icon.icns"
        if icns.exists():
            cmd.extend(["--icon", str(icns)])

print(f"Building {'GUI' if not cli_mode else 'CLI'} version...")
print(f"Entry: {entry}")
print()

subprocess.run(cmd, cwd=ROOT, check=True)

print(f"\nBuilt: dist/{name}")

if sys.platform == "darwin" and not cli_mode:
    # Inject LSUIElement to hide dock icon
    import plistlib
    plist_path = ROOT / "dist" / f"{name}.app" / "Contents" / "Info.plist"
    if plist_path.exists():
        with open(plist_path, "rb") as f:
            plist = plistlib.load(f)
        plist["LSUIElement"] = True
        plist["CFBundleDisplayName"] = "eLOQ Sync"
        plist["CFBundleShortVersionString"] = "1.0.0"
        with open(plist_path, "wb") as f:
            plistlib.dump(plist, f)
        print("  Plist updated (LSUIElement, display name, version)")
    print(f"  App bundle: dist/{name}.app")
