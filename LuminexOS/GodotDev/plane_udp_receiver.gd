extends Node

signal planes_received(planes: Array)

const PORT = 5007

var udp := PacketPeerUDP.new()

func _ready():
	var err = udp.bind(PORT)
	if err != OK:
		print("Failed to bind UDP port ", PORT, " error: ", err)
	else:
		print("Plane UDP listening on port ", PORT)

func _process(_delta):
	while udp.get_available_packet_count() > 0:
		var bytes = udp.get_packet()
		var message = bytes.get_string_from_utf8()

		var json = JSON.new()
		var parse_result = json.parse(message)

		if parse_result != OK:
			print("Failed to parse plane JSON")
			continue

		var data = json.get_data()

		if data.has("planes"):
			emit_signal("planes_received", data["planes"])
