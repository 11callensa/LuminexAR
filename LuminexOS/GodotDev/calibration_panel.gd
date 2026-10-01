extends Control

@export var udp_receiver: Node
@export var bars_row: Node

func _ready():
	if udp_receiver:
		udp_receiver.calibration_status_received.connect(bars_row.update_status)
