#!/usr/bin/env bash
# Deploy the Mac's current branch to the Pi. Run on the Mac, after pushing.
#
#   scripts/deploy.sh            export the app, update the Pi's code, copy the app over
#   scripts/deploy.sh --build    also rebuild the native programs on the Pi
#                                (needed when Head_Tracker or CAPE_depth code changed)
#
# The code reaches the Pi through git (so it always matches a pushed commit); only the
# exported app, which is build output and not in git, is copied over with rsync.
# Override the defaults with GODOT, PI_HOST and PI_REPO environment variables.
set -euo pipefail

GODOT="${GODOT:-/Applications/Godot.app/Contents/MacOS/Godot}"
PI_HOST="${PI_HOST:-LuminexPi}"
PI_REPO="${PI_REPO:-/home/alex/Documents/Luminex}"
APP="LuminexOS/Pi/GlassesAR.arm64"

REPO_DIR="$(cd "$(dirname "$(realpath "$0")")/.." && pwd)"
cd "$REPO_DIR"

fail() { echo "ERROR: $1" >&2; exit 1; }

build=false
case "${1:-}" in
	"") ;;
	--build) build=true ;;
	*) fail "Unknown option $1 (usage: scripts/deploy.sh [--build])" ;;
esac

# --- What is being deployed ---
branch="$(git branch --show-current)"
[[ -n "$branch" ]] || fail "Not on a branch (detached HEAD)."
commit="$(git rev-parse --short HEAD)"
dirty=no
[[ -z "$(git status --porcelain)" ]] || dirty=yes

# The Pi pulls from GitHub, so the commit must be pushed or the code would not match the app.
git fetch -q origin
[[ "$(git rev-parse HEAD)" == "$(git rev-parse "origin/$branch" 2>/dev/null)" ]] \
	|| fail "$branch at $commit is not pushed (or is behind origin). Push first."

echo "Deploying branch $branch at $commit (uncommitted changes: $dirty) to $PI_HOST"
[[ "$dirty" == no ]] || echo "WARNING: the app is exported from your working tree, so it includes uncommitted changes the Pi's code does not have."

# --- Export the app ---
echo "Exporting release build..."
"$GODOT" --headless --path LuminexOS/GodotDev --export-release "Linux" "../Pi/GlassesAR.arm64" > /dev/null 2>&1 \
	|| fail "Godot export failed. Run it in the editor to see why."
file "$APP" | grep -q "ARM aarch64" || fail "Export did not produce an arm64 binary at $APP."

# --- Update the Pi's code ---
echo "Updating the Pi's code..."
ssh "$PI_HOST" "cd '$PI_REPO' && [ -z \"\$(git status --porcelain)\" ]" \
	|| fail "The Pi's checkout has uncommitted changes (or is unreachable). Never edit code on the Pi; inspect with: ssh $PI_HOST 'cd $PI_REPO && git status'"
ssh "$PI_HOST" "cd '$PI_REPO' && git fetch -q origin && git switch -q '$branch' && git pull -q --ff-only" \
	|| fail "Could not check out $branch on the Pi."

# --- Copy the app (after the pull, which removes the old tracked copy the first time) ---
echo "Copying the app..."
rsync -az "$APP" "$PI_HOST:$PI_REPO/$APP"

if $build; then
	echo "Rebuilding native programs on the Pi..."
	ssh "$PI_HOST" "cd '$PI_REPO' && ./setup.sh --build-only"
fi

# --- Record what is on the Pi ---
ssh "$PI_HOST" "cat > '$PI_REPO/DEPLOYED'" <<EOF
branch: $branch
commit: $commit
deployed: $(date -u +%Y-%m-%dT%H:%M:%SZ)
uncommitted changes: $dirty
EOF

echo "Done. The Pi is on $branch at $commit; launch from the desktop icon."
