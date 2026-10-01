extends Node

signal head_orientation_received(orientation: Quaternion)

const PORT = 5008

var udp := PacketPeerUDP.new()

func _ready():
	var err = udp.bind(PORT)
	if err != OK:
		print("Failed to bind UDP port ", PORT, " error: ", err)
	else:
		print("Head orientation UDP listening on port ", PORT)

func _process(_delta):
	while udp.get_available_packet_count() > 0:
		var bytes = udp.get_packet()
		var message = bytes.get_string_from_utf8()

		var json = JSON.new()
		var parse_result = json.parse(message)

		if parse_result != OK:
			continue

		var data = json.get_data()

		if data.has("orientation"):
			var o = data["orientation"]
			print("RAW: ", o)
			var q = Quaternion(o[1], o[2], o[3], o[0])
			emit_signal("head_orientation_received", q)
