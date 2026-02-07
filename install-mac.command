#!/bin/bash
# eLOQ Sync — macOS first-launch helper
# Double-click this file to remove quarantine and launch the app.

DIR="$(cd "$(dirname "$0")" && pwd)"
APP="$DIR/eLOQ Sync.app"

if [ ! -d "$APP" ]; then
    echo "Error: 'eLOQ Sync.app' not found next to this script."
    echo "Make sure both files are in the same folder."
    read -p "Press Enter to close..."
    exit 1
fi

echo "Removing macOS quarantine flag..."
xattr -cr "$APP"
echo "Done. Launching eLOQ Sync..."
open "$APP"
exit 0
