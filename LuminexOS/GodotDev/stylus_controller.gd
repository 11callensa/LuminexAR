extends Node3D

signal calibrated

@export var target_rest_euler_degrees: Vector3 = Vector3(0, 0, 0)

var calibration_offset := Quaternion.IDENTITY
var is_calibrated := false


# Restored — orientation is back to coming from the IMU via
# UDPReceiver's state_received signal.
func _on_state_received(raw_rotation: Quaternion, wheel: int, wheel_click: bool, mode_button: bool):
	var imu_rotation = Quaternion(
		raw_rotation.y,
		-raw_rotation.x,
		-raw_rotation.z,
		-raw_rotation.w
	)

	if is_calibrated:
		quaternion = calibration_offset * imu_rotation
	else:
		quaternion = imu_rotation

	# calibrate() is no longer triggered here directly — GameManager
	# decides when a wheel click should count as a calibration action,
	# based on which panel is currently active.


# ArUco-era: wheel/buttons used to arrive on their own signal
# (UDPReceiver no longer emits buttons_received — wheel_click now
# comes through state_received above instead). Left here for reference.
# func _on_udp_receiver_buttons_received(wheel: int, wheel_click: bool, mode_button: bool):
# 	if wheel_click:
# 		calibrate()


# ArUco-era: position/orientation used to come from stylus_tracker.py
# via StylusTipReceiver. Not currently connected to anything — left
# here in case ArUco tracking is revisited later.
# func _on_stylus_tip_receiver_tip_updated(is_visible: bool, tip_position: Vector3, tip_orientation: Quaternion):
# 	if not is_visible:
# 		return
# 	position = tip_position
# 	set_orientation(tip_orientation)
#
# func set_orientation(new_rotation: Quaternion):
# 	if is_calibrated:
# 		quaternion = calibration_offset * new_rotation
# 	else:
# 		quaternion = new_rotation


func calibrate():
	if is_calibrated:
		return

	var target_rotation = Quaternion.from_euler(Vector3(
		deg_to_rad(target_rest_euler_degrees.x),
		deg_to_rad(target_rest_euler_degrees.y),
		deg_to_rad(target_rest_euler_degrees.z)
	))

	calibration_offset = target_rotation * quaternion.inverse()
	is_calibrated = true

	emit_signal("calibrated")
	print("Stylus calibrated")


func reset_calibration():
	calibration_offset = Quaternion.IDENTITY
	is_calibrated = false


func set_position_from_tracker(new_position: Vector3):
	position = new_position


func _on_stylus_tip_receiver_tip_updated(is_visible: bool, tip_position: Vector3, tip_orientation: Quaternion):
	if not is_visible:
		return

	# Orientation comes from the IMU (see _on_state_received) — the
	# orientation data in this signal is intentionally ignored.
	set_position_from_tracker(tip_position)
