#!/usr/bin/env bash
# Launch the GlassesAR app fullscreen on the glasses, inside the repo's .venv.
# Run by the desktop icon (see install_desktop_launcher.sh). There is no terminal,
# so output goes to logs/glasses.log; quit the app with Alt+F4.
set -eo pipefail

REPO_DIR="$(cd "$(dirname "$(realpath "$0")")/.." && pwd)"
cd "$REPO_DIR"

source .venv/bin/activate

mkdir -p logs
exec LuminexOS/Pi/GlassesAR.sh --fullscreen "$@" > logs/glasses.log 2>&1
