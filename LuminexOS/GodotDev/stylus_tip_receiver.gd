extends Node

signal tip_updated(visible: bool, position: Vector3, orientation: Quaternion)

const PORT = 5006

# Represents a 180° rotation about X — the change of basis between
# OpenCV's camera convention (x right, y down, z forward) and Godot's
# (x right, y up, z backward). Used to correctly convert orientation,
# not just flip signs naively.
const AXIS_FLIP := Quaternion(1, 0, 0, 0)

var udp := PacketPeerUDP.new()

func _ready():
	var err = udp.bind(PORT)
	if err != OK:
		print("Failed to bind UDP port ", PORT, " error: ", err)
	else:
		print("Stylus tip UDP listening on port ", PORT)

func _process(_delta):
	while udp.get_available_packet_count() > 0:
		var bytes = udp.get_packet()
		var message = bytes.get_string_from_utf8()

		var json = JSON.new()
		var parse_result = json.parse(message)

		if parse_result != OK:
			continue

		var data = json.get_data()

		var is_visible = data.get("visible", false)

		if is_visible and data.get("position") != null and data.get("orientation") != null:
			var pos = data["position"]
			var tip_pos = _convert_point(pos[0], pos[1], pos[2])

			var ori = data["orientation"]
			var tip_orientation = _convert_orientation(ori[0], ori[1], ori[2], ori[3])

			emit_signal("tip_updated", true, tip_pos, tip_orientation)
		else:
			emit_signal("tip_updated", false, Vector3.ZERO, Quaternion.IDENTITY)


func _convert_point(x: float, y: float, z: float) -> Vector3:
	return Vector3(x, -y, -z)


# data arrives as [w, x, y, z] from Python
func _convert_orientation(w: float, x: float, y: float, z: float) -> Quaternion:
	var cam_quat = Quaternion(x, y, z, w)
	return AXIS_FLIP * cam_quat * AXIS_FLIP
