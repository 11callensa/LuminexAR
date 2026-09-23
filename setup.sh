#!/usr/bin/env bash

set -e

echo "========================================="
echo "       LuminexAR Setup"
echo "========================================="

# ======= Configuration =======
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"

echo
echo "Project directory:"
echo "$PROJECT_DIR"

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

# ======= XREAL driver build dependencies =======
echo
echo "Installing XREAL driver build dependencies..."

sudo apt install -y \
    cmake \
    build-essential \
    libjson-c-dev

# ======= Git submodules =======
echo
echo "Initialising Git submodules..."

cd "$PROJECT_DIR"

git submodule update --init --recursive

# ======= XREAL driver =======
echo
echo "Building XREAL Air Linux driver..."

cd "$PROJECT_DIR/nrealAirLinuxDriver"

rm -rf build
mkdir build
cd build

cmake ..
make -j"$(nproc)"

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
echo "========================================="
echo "       LuminexAR setup complete!"
echo "========================================="

echo
echo "Activate the environment with:"
echo
echo "source $VENV_DIR/bin/activate"
echo