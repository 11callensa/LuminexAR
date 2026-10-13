# 0002 — Placement of LuminexArduino and Camera_Tools

- **Status:** Proposed
- **Date:** 2026-10-13

## Context

The target layout (`pi/`, `editor/`, `shared/`, `scripts/`, `docs/`) has no obvious home for
two directories:

- `LuminexArduino/Spatial_Stylus/` — firmware flashed onto the stylus from the Arduino IDE.
  It never runs on the Pi or in Godot.
- `LuminexScripts/Camera_Tools/` — Python calibration scripts (`rgb_cam_calibration.py`,
  `depth_intrinsics.py`) run on the Pi with the cameras attached, plus their output
  `rgb_camera_instrinsics.json`, which the runtime consumes.

## Decision (proposed)

1. **`LuminexArduino/` → `firmware/stylus/`.** A fourth top-level runtime alongside `pi/`
   and `editor/`: it targets different hardware with a different toolchain. Keeping it out
   of `pi/` keeps "what runs on the Pi" honest. The stylus speaks the same BLE `STATE;...`
   format that `pi/` parses, so that format belongs in `shared/` too.
2. **`Camera_Tools/` scripts → `pi/tools/calibration/`.** They run on the Pi against Pi
   hardware but are one-off tools, not services the app launches.
3. **Calibration output → `shared/` (or a single config directory)**, renamed to
   `rgb_camera_intrinsics.json` (fixing the typo). Intrinsics are config consumed by
   several programs and should live in one place, not next to the script that produced them.

## Consequences

- Top level becomes `pi/ editor/ firmware/ shared/ scripts/ docs/`.
- Moves happen as part of the layout migration, not before.
- Any code reading `rgb_camera_instrinsics.json` must be updated with the move.
