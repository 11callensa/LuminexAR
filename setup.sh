#!/usr/bin/env bash
#
# LuminexAR setup. Run once on a fresh Raspberry Pi; safe to re-run.
#
#   ./setup.sh               full setup
#   ./setup.sh --build-only  only rebuild the native programs (Head_Tracker, CAPE_depth)

set -e

BUILD_ONLY=0
if [[ "${1:-}" == "--build-only" ]]; then
    BUILD_ONLY=1
fi

echo "========================================="
echo "       LuminexAR Setup"
echo "========================================="

# ======= Configuration =======
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"

# Native programs built from source (each has its own CMakeLists.txt)
NATIVE_PROJECTS=(
    "LuminexScripts/Head_Tracker"
    "LuminexScripts/Depth_Camera/CAPE_depth"
)

echo
echo "Project directory:"
echo "$PROJECT_DIR"

build_native_projects() {
    for project in "${NATIVE_PROJECTS[@]}"; do
        echo
        echo "Building $project..."

        cmake -S "$PROJECT_DIR/$project" -B "$PROJECT_DIR/$project/build" -DCMAKE_BUILD_TYPE=Release
        cmake --build "$PROJECT_DIR/$project/build" -j"$(nproc)"
    done
}

if [[ "$BUILD_ONLY" -eq 1 ]]; then
    build_native_projects
    echo
    echo "Native programs rebuilt."
    exit 0
fi

# ======= Check operating system =======
if [[ "$(uname -m)" != "aarch64" ]]; then
    echo "ERROR: LuminexAR currently requires an aarch64 system."
    exit 1
fi

if [[ ! -f /etc/os-release ]]; then
    echo "ERROR: Cannot determine operating system."
    exit 1
fi

source /etc/os-release

echo
echo "Operating system: $PRETTY_NAME"
echo "Architecture: $(uname -m)"

# ======= Update package information =======
echo
echo "Updating apt package information..."

sudo apt update

# ======= Hailo system packages =======
echo
echo "Checking Hailo system packages..."

sudo apt install -y \
    hailo-all \
    hailo-models \
    hailo-tappas-core \
    python3-hailo-tappas \
    python3-hailort \
    hailort \
    hailort-pcie-driver \
    rpicam-apps-hailo-postprocess

# ======= Arducam system packages =======
echo
echo "Installing Arducam system packages..."

sudo apt install -y \
    arducam-config-parser-dev \
    arducam-evk-sdk-dev \
    arducam-tof-sdk-dev

# ======= Native build dependencies =======
echo
echo "Installing native build dependencies..."

# XREAL driver library (Head_Tracker)
sudo apt install -y \
    cmake \
    build-essential \
    libjson-c-dev \
    libusb-1.0-0-dev \
    libhidapi-dev

# CAPE plane detection (CAPE_depth)
sudo apt install -y \
    libopencv-dev \
    libeigen3-dev

# ======= Git submodules =======
echo
echo "Initialising Git submodules..."

cd "$PROJECT_DIR"

git submodule update --init --recursive

# ======= XREAL glasses udev rules =======
echo
echo "Installing XREAL glasses udev rules..."

RULES_CHANGED=0
for rule in "$PROJECT_DIR"/nrealAirLinuxDriver/udev/*.rules; do
    [[ -e "$rule" ]] || continue
    dest="/etc/udev/rules.d/$(basename "$rule")"
    if ! cmp -s "$rule" "$dest" 2>/dev/null; then
        sudo cp "$rule" "$dest"
        RULES_CHANGED=1
        echo "Installed $(basename "$rule")"
    fi
done

if [[ "$RULES_CHANGED" -eq 1 ]]; then
    sudo udevadm control --reload-rules
    sudo udevadm trigger
    echo "Rules updated. Unplug and replug the glasses once."
else
    echo "Already installed."
fi

# ======= Native programs =======
# Built in their own folders. Submodules (nrealAirLinuxDriver, CAPE) are
# used as libraries and never modified or built inside.
build_native_projects

# ======= Python virtual environment =======
echo
echo "Setting up Python virtual environment..."

if [[ ! -d "$VENV_DIR" ]]; then
    python3 -m venv --system-site-packages "$VENV_DIR"
else
    echo "Existing .venv found — keeping it."
fi

source "$VENV_DIR/bin/activate"

echo
echo "Python:"
python --version

# ======= PyTorch =======
echo
echo "Installing PyTorch 2.14.0..."

python -m pip install torch==2.14.0 --extra-index-url https://www.piwheels.org/simple

# ======= Ultralytics =======
echo
echo "Installing Ultralytics..."

python -m pip install ultralytics==8.4.160

# ======= Bleak =======
echo
echo "Installing Bleak..."

python -m pip install bleak

# ======= Hailo Apps =======
echo
echo "Installing hailo-apps..."

python -m pip install -e "$PROJECT_DIR/hailo-apps"

# ======= Arducam Python package =======
echo
echo "Installing ArducamDepthCamera..."

python -m pip install ArducamDepthCamera==0.1.24

# ======= Verification =======
echo
echo "========================================="
echo "       Verifying installation"
echo "========================================="

echo
echo "Testing PyTorch..."

python -c \
"import torch; print('PyTorch:', torch.__version__)"

echo
echo "Testing Ultralytics..."

python -c \
"import ultralytics; print('Ultralytics:', ultralytics.__version__)"

echo
echo "Testing Hailo platform..."

python -c \
"import hailo_platform; print('Hailo platform: OK')"

echo
echo "Testing Hailo apps..."

python -c \
"from hailo_apps.python.core.common import toolbox; print('Hailo apps: OK')"

echo
echo "Testing Arducam..."

python -c \
"import ArducamDepthCamera; print('ArducamDepthCamera: OK')"

echo
echo "Testing native programs..."

for exe in \
    "LuminexScripts/Head_Tracker/build/xrealAirHeadTracker" \
    "LuminexScripts/Depth_Camera/CAPE_depth/build/cape_tof"; do
    if [[ -x "$PROJECT_DIR/$exe" ]]; then
        echo "$(basename "$exe"): OK"
    else
        echo "ERROR: $exe was not built."
        exit 1
    fi
done

echo
echo "========================================="
echo "       LuminexAR setup complete!"
echo "========================================="

echo
echo "Activate the environment with:"
echo
echo "source $VENV_DIR/bin/activate"
echo
