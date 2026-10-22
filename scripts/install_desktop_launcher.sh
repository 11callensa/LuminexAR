#!/usr/bin/env bash
# Put a "Luminex Glasses" icon on the Pi desktop that runs scripts/launch_glasses.sh.
# The .desktop file needs absolute paths, so it is generated here rather than committed.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$(realpath "$0")")/.." && pwd)"
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
DESKTOP_FILE="$DESKTOP_DIR/luminex-glasses.desktop"

mkdir -p "$DESKTOP_DIR"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Luminex Glasses
Comment=Launch the GlassesAR app on the XREAL glasses
Exec=$REPO_DIR/scripts/launch_glasses.sh
Icon=$REPO_DIR/LuminexOS/GodotDev/icon.svg
Terminal=false
Categories=Graphics;
EOF

chmod +x "$DESKTOP_FILE"
# Marks the launcher as trusted so the file manager runs it instead of asking.
gio set "$DESKTOP_FILE" metadata::trusted true 2>/dev/null || true

echo "Installed $DESKTOP_FILE"
