#!/usr/bin/env bash
# Launch the GlassesAR app fullscreen on the glasses, inside the repo's .venv.
# Run by the desktop icon (see install_desktop_launcher.sh). There is no terminal,
# so output goes to logs/glasses.log; quit the app with Alt+F4.
# --calibrate opens the glasses alignment panel first ("Luminex Calibrate" icon);
# any other arguments are passed on to Godot.
#
# Steps: find the glasses' display, switch them to stereo (they wake up in 2D),
# wait for the 3840x1080 mode, then start the app and tell it where the glasses
# are on the desktop so it can go fullscreen there rather than on another monitor.
# The glasses disconnect entirely while asleep, so they must be worn at launch.
set -eo pipefail

REPO_DIR="$(cd "$(dirname "$(realpath "$0")")/.." && pwd)"
cd "$REPO_DIR"

DISPLAY_MODE_TOOL="LuminexScripts/Head_Tracker/build/xrealAirDisplayMode"
STEREO_MODE="3840x1080"
STEREO_WAIT_SECONDS=10

mkdir -p logs
exec > logs/glasses.log 2>&1

# Shows an error dialog (the launcher has no terminal) and stops.
fail() {
	echo "ERROR: $1"
	if command -v zenity > /dev/null; then
		zenity --error --title="Luminex Glasses" --text="$1" --width=400
	elif command -v notify-send > /dev/null; then
		notify-send "Luminex Glasses" "$1"
	fi
	exit 1
}

# Prints "<current mode> <x,y position>" of the glasses' display, or nothing if absent.
# The output name (HDMI-A-1/2) depends on the port, so match by make instead.
glasses_display() {
	wlr-randr | awk '
		function report() { if (glasses) print mode, pos }
		/^[^ ]/                   { report(); glasses = 0; mode = ""; pos = "" }
		/^  Make: *(Nreal|XREAL)/ { glasses = 1 }
		/^    .*current/          { mode = $1 }
		/^  Position:/            { pos = $2 }
		END                       { report() }
	'
}

source .venv/bin/activate

if [[ -z "$(glasses_display)" ]]; then
	fail "Glasses not detected. Plug them in and put them on (they disconnect while asleep), then try again."
fi

[[ -x "$DISPLAY_MODE_TOOL" ]] || fail "$DISPLAY_MODE_TOOL is missing. Run ./setup.sh --build-only."
"$DISPLAY_MODE_TOOL" 3d || fail "Could not switch the glasses to stereo mode."

# The mode switch briefly reconnects the display, so wait for it to come back in stereo.
for (( i = 0; i < STEREO_WAIT_SECONDS * 2; i++ )); do
	read -r mode position <<< "$(glasses_display)"
	[[ "$mode" == "$STEREO_MODE" ]] && break
	sleep 0.5
done
[[ "$mode" == "$STEREO_MODE" ]] || fail "Glasses did not switch to stereo ($STEREO_MODE); current mode: ${mode:-none}."

echo "Glasses in stereo at desktop position $position"

godot_args=()
app_args=(--glasses-position="$position")
for arg in "$@"; do
	if [[ "$arg" == "--calibrate" ]]; then
		app_args+=(--calibrate)
	else
		godot_args+=("$arg")
	fi
done
exec LuminexOS/Pi/GlassesAR.sh "${godot_args[@]}" -- "${app_args[@]}"
