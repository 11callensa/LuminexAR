# CLAUDE.md

Guidance for Claude Code and for engineers working in this repo.

## Overview

Luminex is a pair of open-source AR CAD glasses: XREAL Air 2 Pro glasses driven by a
Raspberry Pi 5 with a Hailo AI HAT+, an Arducam ToF depth camera, a USB RGB camera and a
BLE spatial stylus (Arduino). The Godot scene is built in the editor on the Mac and
exported as an arm64 app that runs on the Pi, where it launches small sensor services
(head tracking, stylus tracking, plane detection) that stream data to it over UDP. The
repo is portfolio-facing: clarity, modularity and clean history matter as much as working code.

One of the development aims is to maximise user-experience fluidity, frames-per-second, and 
reduce friction. The interface must be intuitive, as I try and build this CAD overlay on top 
of the real world.

## Current layout

```
LuminexOS/GodotDev/      Godot 4.7 project (GlassesAR) — scenes and GDScript
LuminexOS/Pi/            Exported app (GlassesAR.arm64 + GlassesAR.sh) that runs on the Pi
LuminexScripts/
  Head_Tracker/          C: glasses IMU -> UDP (CMake, uses nrealAirLinuxDriver)
  Depth_Camera/CAPE_depth/  C++: ToF depth -> plane detection (CAPE) -> UDP (CMake)
  Stylus/                Python: BLE stylus receiver + ArUco tip tracker -> UDP
  Camera_Tools/          Python: RGB/ToF camera calibration
LuminexArduino/Spatial_Stylus/  Stylus firmware (IMU, rotary encoder, button, BLE)
AI HAT Demos/            Hailo FastSAM/UNET demos — upcoming feature, not integrated
hailo-apps/ CAPE/ Arducam_tof_camera/ nrealAirLinuxDriver/   Third-party git submodules [Essential]
setup.sh                 One-time Pi setup (apt, submodules, native builds, .venv)
shared/                  UDP host, ports and message formats (protocol.json + README)
pyproject.toml           Installs shared/ into .venv (pip install -e .)
docs/decisions/          Architecture decision records
scripts/                 Pi helpers: launch_glasses.sh, install_desktop_launcher.sh
```

### Runtime data flow (all on the Pi, localhost UDP)

`LuminexOS/GodotDev/game_manager.gd` launches each service and listens on its port.
Host, ports and message formats are defined once in `shared/` (`protocol.json`, documented in
`shared/README.md`); never hard-code them.

| Port | Link (`protocol.json`) | Sender                                    | Message                     |
|------|------------------------|-------------------------------------------|-----------------------------|
| 5005 | `stylus_state`         | `Stylus/stylus_receiver.py` (BLE bridge)  | `STATE;...` IMU/buttons     |
| 5006 | `stylus_tip`           | `Stylus/stylus_tracker.py` (ArUco)        | JSON stylus tip pose        |
| 5007 | `planes`               | `CAPE_depth/build/cape_tof --headless`    | JSON `{"planes":[...]}`     |
| 5008 | `head_orientation`     | `Head_Tracker/build/xrealAirHeadTracker`  | JSON `HEAD_ORIENTATION`     |

Note: the ToF camera is mounted upside down and sits 14.5 mm above the RGB camera.

## Target layout (not yet migrated — move nothing without approval)

```
pi/       Glasses runtime that runs on the Pi (stylus, head tracking, depth, ai/)
editor/   Godot project, built and exported on the Mac
shared/   Protocol/message definitions (ports, formats) used by both sides
scripts/  Deploy, logs, run-on-Pi helpers
docs/     Architecture notes and decisions (docs/decisions/)
```

- **Rule: `pi/` and `editor/` only communicate through `shared/`.** `shared/` already
  exists (ports and message formats); it stays at the top level when the rest moves.
- **Hailo AI** goes to `pi/ai/`, developed on branch `feature/hailo-ai` and merged into
  `staging` only once integrated with the app.
- **Legacy code lives in git history**, not in the tree: tag the last commit that has it,
  delete it, and record why in `docs/decisions/` (e.g. `0001-remove-og-depth.md`).
- **Not yet placed:** `LuminexArduino/` and `Camera_Tools/`. Proposed homes are in
  `docs/decisions/0002-arduino-and-camera-tools-placement.md`.

## Setup, run, test

**Pi (Debian 13, aarch64, repo at `/home/alex/Documents/Luminex`, SSH alias `LuminexPi`):**

```bash
./setup.sh               # full setup: apt packages, submodules, udev rules, native builds, .venv
./setup.sh --build-only  # rebuild Head_Tracker and CAPE_depth only
source .venv/bin/activate
LuminexOS/Pi/GlassesAR.sh   # run the app (needs the Pi's display); launches all services
scripts/launch_glasses.sh   # same, fullscreen, logs to logs/glasses.log (quit: Alt+F4)
scripts/install_desktop_launcher.sh   # one-off: desktop icon that runs launch_glasses.sh
```

Standalone, for debugging: `xrealAirHeadTracker [host] [port]` and
`cape_tof --help` (flags include `--headless`, `--udp-host`, `--udp-port`, `--range`).

**Mac:** open `LuminexOS/GodotDev` in Godot 4.7 and export with the "Linux" preset
(writes `LuminexOS/Pi/GlassesAR.arm64`). The Arduino sketch is flashed with the Arduino IDE.
There is no Mac-side Python environment yet (TODO).

**Tests:** none yet (TODO). When added:
- Tests that need the camera, stylus or glasses are marked as hardware tests and skipped by default.
- All other tests must pass on the Mac and on a Pi with no hardware attached.
- Do not build hardware mocks or fake sensor modes.

## Git & deployment

- **The Mac is the single source of truth.** Never edit code on the Pi; it is a run target.
- **Branches:** `staging` is the default working branch. New work goes on feature branches;
  use git worktrees for parallel work. `main` and `staging` have diverged (each has
  commits the other lacks) — reconcile only when asked.
- **Deploying today:** push from the Mac, then `git pull` on the Pi.
- **Deploying (planned, `scripts/deploy.sh`, TODO):**
  - Default: rsync the Mac working tree to the Pi and write a `DEPLOYED` file on the Pi
    (branch, commit, timestamp, whether there were uncommitted changes).
  - `scripts/deploy.sh --branch <name>`: check out a pushed branch via git on the Pi.
- **Before any deploy**, state which branch and commit are going to the Pi. Never deploy
  or change the Pi's branch unless asked.
- **Before touching the Pi's checkout**, run `git status` there and stop if it has
  uncommitted changes.
- **Commits:** small and logical, imperative subject line (e.g. "Add CAPE plane UDP output").
  Never force-push. Never commit secrets.
- **Don't commit build output or models.** `build/` folders, logs and model files
  (`.hef`, `.har`, `.onnx`, `.pt`, `.zip` of models) stay out of git. Exception until
  `deploy.sh` exists: `LuminexOS/Pi/GlassesAR.arm64` is how the app reaches the Pi, so
  commit it only when asked, in its own commit. Removing already-committed binaries and
  models is a separate, approved change.
- **Submodules** are third-party: never edit or build inside them (CMake builds into
  each project's own `build/`).

## Hardware

- The glasses, cameras and stylus are often **not** connected to the Pi.
- Only run code or tests that rely on the camera, stylus or glasses when Alex says the hardware is connected to the Pi.

## Code standards

- Modular: small, single-purpose files and functions.
- Types wherever the language supports them (Python type hints, typed GDScript).
- Docstrings/comments on public functions; explain *why*, not *what*.
- Tests alongside new features (see Tests above).
- No dead code: no commented-out alternatives or unused files — git history keeps them.
- Config (ports, calibration, camera intrinsics) belongs in one place, not scattered constants; `shared/` owns protocol values.
- Prefer editing existing code over adding new frameworks or dependencies.

## Working style

- **Propose before acting.** Before editing files, committing, pushing, installing anything or running anything on the Pi, outline:
  1. the proposed changes,
  2. why they are needed or beneficial,
  3. any points of improvement or risks noticed along the way,
  then wait for approval. Read-only investigation (reading files, `git status`, `git log`)
  needs no approval. Steps inside an already-approved plan don't need re-approval.
- Plan before large changes; ask when requirements are unclear rather than guessing.
- Keep explanations brief.

## Never

- Edit code directly on the Pi.
- Force-push, or rewrite pushed history.
- Commit secrets, model files or build output (see exception above).
- Edit inside git submodules.
- Add heavy dependencies without asking.
- Delete files without asking.
- Deploy to the Pi or change its branch without being asked.
- Run hardware-dependent code unless told the hardware is connected.
