class_name GlassesCalibration
extends RefCounted

## How the glasses' RGB camera and displays relate to the wearer's eyes. Camera data
## (planes, stylus tip) is moved into world space through camera_to_head(), and the eye
## cameras use eye_fov. Tuned in calibration mode ("Luminex Calibrate") and saved on the
## Pi under user://, so deploys never overwrite it. The defaults are the measured
## starting point for a fresh install.

const SAVE_PATH := "user://glasses_calibration.json"

## Vertical field of view of each eye, degrees. Air 2 Pro: 46 deg diagonal at 16:9.
var eye_fov: float = 23.5
## Angles of the camera relative to the line of sight, degrees.
var yaw: float = 0.0
var pitch: float = 0.0
var roll: float = 0.0
## RGB camera position relative to the midpoint between the eyes, metres, in Godot axes
## (x right, y up, z backwards). Measured: centred, ~30 mm above, ~20 mm in front.
var camera_offset := Vector3(0.0, 0.03, -0.02)


## Transform from the RGB camera's frame (Godot axes) to the head frame.
func camera_to_head() -> Transform3D:
	var angles := Vector3(deg_to_rad(pitch), deg_to_rad(yaw), deg_to_rad(roll))
	return Transform3D(Basis.from_euler(angles), camera_offset)


func save() -> bool:
	var file := FileAccess.open(SAVE_PATH, FileAccess.WRITE)
	if file == null:
		push_error("Could not save calibration to " + SAVE_PATH)
		return false
	file.store_string(JSON.stringify({
		"eye_fov": eye_fov, "yaw": yaw, "pitch": pitch, "roll": roll,
		"camera_offset": [camera_offset.x, camera_offset.y, camera_offset.z],
	}, "  "))
	print("Calibration saved to ", ProjectSettings.globalize_path(SAVE_PATH))
	return true


## The saved calibration, or the defaults if none has been saved yet.
static func load_or_default() -> GlassesCalibration:
	var calibration := GlassesCalibration.new()
	if not FileAccess.file_exists(SAVE_PATH):
		print("No saved calibration; using defaults")
		return calibration

	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(SAVE_PATH))
	if not data is Dictionary:
		push_error("Unreadable calibration file " + SAVE_PATH + "; using defaults")
		return calibration

	calibration.eye_fov = data.get("eye_fov", calibration.eye_fov)
	calibration.yaw = data.get("yaw", calibration.yaw)
	calibration.pitch = data.get("pitch", calibration.pitch)
	calibration.roll = data.get("roll", calibration.roll)
	var offset: Array = data.get("camera_offset", [])
	if offset.size() == 3:
		calibration.camera_offset = Vector3(offset[0], offset[1], offset[2])
	print("Loaded calibration from ", ProjectSettings.globalize_path(SAVE_PATH))
	return calibration
