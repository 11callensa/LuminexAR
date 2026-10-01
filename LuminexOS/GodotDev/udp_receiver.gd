extends Node

signal stylus_connected
signal stylus_disconnected
signal state_received(rotation, wheel, wheel_click, mode_button)
signal calibration_status_received(sys, gyro, accel, mag)

const PORT = 5005

var udp := PacketPeerUDP.new()
var _has_signaled_connected := false

func _ready():
	var err = udp.bind(PORT)
	if err != OK:
		print("Failed to bind UDP port ", PORT, " error: ", err)
	else:
		print("UDP listening on port ", PORT)

func _process(_delta):
	while udp.get_available_packet_count() > 0:
		var bytes = udp.get_packet()
		var message = bytes.get_string_from_utf8()
		_handle_message(message)

func _handle_message(message: String):
	if message == "CONNECTED":
		print("Stylus Connected received")
		_has_signaled_connected = true
		emit_signal("stylus_connected")
		return

	if message == "DISCONNECTED":
		print("Stylus Disconnected received")
		_has_signaled_connected = false
		emit_signal("stylus_disconnected")
		return

	if message.begins_with("STATE;"):
		var payload = message.substr(6)
		var parts = payload.split(";")

		if parts.size() == 5:
			var quat_parts = parts[0].split(",")

			if quat_parts.size() == 4:
				var w = float(quat_parts[0])
				var x = float(quat_parts[1])
				var y = float(quat_parts[2])
				var z = float(quat_parts[3])

				var wheel = int(parts[1])
				var wheel_click = parts[2] == "1"
				var mode_button = parts[3] == "1"

				# Infer connection from actually receiving valid state data —
				# covers the case where StylusReceiver.py was already running
				# (and already sent its one-time CONNECTED message) before
				# this Godot session started listening.
				if not _has_signaled_connected:
					_has_signaled_connected = true
					print("Inferred stylus connection from incoming STATE data")
					emit_signal("stylus_connected")

				emit_signal(
					"state_received",
					Quaternion(x, y, z, w),
					wheel,
					wheel_click,
					mode_button
				)

			var cal_parts = parts[4].split(",")
			if cal_parts.size() == 4:
				emit_signal(
					"calibration_status_received",
					int(cal_parts[0]),
					int(cal_parts[1]),
					int(cal_parts[2]),
					int(cal_parts[3])
				)
