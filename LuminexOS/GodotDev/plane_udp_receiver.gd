extends Node

signal planes_received(planes: Array)

var port: int = Protocol.port("planes")

var udp := PacketPeerUDP.new()

func _ready():
	var err = udp.bind(port)
	if err != OK:
		print("Failed to bind UDP port ", port, " error: ", err)
	else:
		print("Plane UDP listening on port ", port)

func _process(_delta):
	# Each message is a complete snapshot, so only the newest one is worth rebuilding
	# the plane meshes for.
	var latest: PackedByteArray
	while udp.get_available_packet_count() > 0:
		latest = udp.get_packet()
	if latest.is_empty():
		return

	var json = JSON.new()
	if json.parse(latest.get_string_from_utf8()) != OK:
		print("Failed to parse plane JSON")
		return

	var data = json.get_data()

	if data.has("planes"):
		emit_signal("planes_received", data["planes"])
