# shared/

The contract between the glasses runtime on the Pi and the Godot app. Both sides read
host and ports from [`protocol.json`](protocol.json); nothing else should hard-code them.

- **Python:** `from shared import protocol` → `protocol.HOST`, `protocol.port("planes")`
  (installed into `.venv` by `setup.sh` via `pip install -e .`).
- **Godot:** `Protocol.host()`, `Protocol.port("planes")` (`LuminexOS/GodotDev/protocol.gd`).
- **Native services** (`xrealAirHeadTracker`, `cape_tof`) take host and port as command-line
  arguments; `game_manager.gd` passes them from `protocol.json` at launch. Their built-in
  defaults exist only for running them standalone while debugging.

## Messages

All links are UDP datagrams to `host`, one UTF-8 message per datagram, Pi service → Godot.

### `stylus_state` (5005) — `Stylus/stylus_receiver.py`

Plain text. Lifecycle messages `CONNECTED` and `DISCONNECTED`, and every BLE notification:

```
STATE;<w>,<x>,<y>,<z>;<wheel>;<wheel_click>;<mode_button>;<sys>,<gyro>,<accel>,<mag>
```

Quaternion from the stylus IMU, wheel as an integer count, buttons as `0`/`1`, and the
IMU calibration levels (0–3) for system, gyroscope, accelerometer and magnetometer.

The stylus firmware (`LuminexArduino/Spatial_Stylus`) sends the receiver its own BLE format:
`Q:<w>,<x>,<y>,<z>;W:<wheel>;WC:<wheel_click>;MB:<mode_button>;CAL:<sys>,<gyro>,<accel>,<mag>`.

### `stylus_tip` (5006) — `Stylus/stylus_tracker.py`

JSON, sent every camera frame:

```json
{"type": "STYLUS_POS", "visible": true, "position": [x, y, z],
 "orientation": [w, x, y, z], "markers_visible": 3}
```

When the stylus is not visible, `position` and `orientation` are `null` and
`markers_visible` is `0`. OpenCV camera frame (x right, y down, z forward), metres.

### `planes` (5007) — `CAPE_depth/build/cape_tof`

JSON, sent every frame (empty list when nothing is found):

```json
{"planes": [{"id": 3, "centroid": [x, y, z], "normal": [nx, ny, nz],
             "corners_flat": [x1, y1, z1, ...]}]}
```

RGB camera frame (ToF offset applied), metres by default. Normals face the camera; IDs are
stable across frames.

### `head_orientation` (5008) — `Head_Tracker/build/xrealAirHeadTracker`

JSON: `{"type": "HEAD_ORIENTATION", "orientation": [w, x, y, z]}`.
