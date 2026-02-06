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

cli_mode = "--cli" in sys.argv
entry = "server.py" if cli_mode else "app.py"
name = "RayonicsKeyReader"

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--onefile",
    "--name", name,
    "--add-data", f"static{':' if sys.platform != 'win32' else ';'}static",
    "--hidden-import", "bleak",
    "--hidden-import", "aiohttp",
    entry,
]

if not cli_mode:
    # Hide console window on Windows, make .app on macOS
    if sys.platform == "win32":
        cmd.append("--noconsole")
    elif sys.platform == "darwin":
        cmd.extend(["--windowed"])

print(f"Building {'GUI' if not cli_mode else 'CLI'} version...")
print(f"Entry: {entry}")
print(f"Command: {' '.join(cmd)}")
print()

subprocess.run(cmd, cwd=ROOT, check=True)

print(f"\nBuilt: dist/{name}")
if sys.platform == "darwin" and not cli_mode:
    print(f"  App bundle: dist/{name}.app")
