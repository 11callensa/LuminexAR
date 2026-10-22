extends Node

signal head_orientation_received(orientation: Quaternion)

var port: int = Protocol.port("head_orientation")

var udp := PacketPeerUDP.new()

func _ready():
	var err = udp.bind(port)
	if err != OK:
		print("Failed to bind UDP port ", port, " error: ", err)
	else:
		print("Head orientation UDP listening on port ", port)

func _process(_delta):
	# The IMU sends ~1000 packets/s; only the newest orientation matters for this frame,
	# so drain the queue and parse just the last one.
	var latest: PackedByteArray
	while udp.get_available_packet_count() > 0:
		latest = udp.get_packet()
	if latest.is_empty():
		return

	var json = JSON.new()
	if json.parse(latest.get_string_from_utf8()) != OK:
		return

	var data = json.get_data()

	if data.has("orientation"):
		var o = data["orientation"]
		var q = Quaternion(o[1], o[2], o[3], o[0])
		emit_signal("head_orientation_received", q)
