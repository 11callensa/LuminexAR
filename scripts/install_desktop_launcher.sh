#!/usr/bin/env bash
# Put two icons on the Pi desktop: "Luminex Glasses" runs scripts/launch_glasses.sh, and
# "Luminex Calibrate" runs it with --calibrate to align the glasses before plane selection.
# The .desktop files need absolute paths, so they are generated here rather than committed.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$(realpath "$0")")/.." && pwd)"
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"

# Writes one launcher: <file name> <title> <description> <launch_glasses.sh arguments>
install_launcher() {
	local desktop_file="$DESKTOP_DIR/$1.desktop"
	cat > "$desktop_file" <<EOF
[Desktop Entry]
Type=Application
Name=$2
Comment=$3
Exec=$REPO_DIR/scripts/launch_glasses.sh $4
Icon=$REPO_DIR/LuminexOS/GodotDev/icon.svg
Terminal=false
Categories=Graphics;
EOF
	chmod +x "$desktop_file"
	# Marks the launcher as trusted so the file manager runs it instead of asking.
	gio set "$desktop_file" metadata::trusted true 2>/dev/null || true
	echo "Installed $desktop_file"
}

mkdir -p "$DESKTOP_DIR"
install_launcher luminex-glasses "Luminex Glasses" "Launch the GlassesAR app on the XREAL glasses" ""
install_launcher luminex-calibrate "Luminex Calibrate" "Align the glasses with the real world, then launch" "--calibrate"
