class_name DimensionLabel
extends Label3D

## A length readout in millimetres that floats beside a measured segment. It is a 3D
## node, so it sits at the right depth in both eyes, and it always faces the viewer.
## "Live" is bold and bright while the user is drawing; "set" is smaller and dimmer once
## the segment is committed, so finished dimensions do not compete with the live one.

const LIVE_FONT_SIZE := 56
const SET_FONT_SIZE := 40
const LIVE_COLOR := Color(1, 1, 1, 1)
const SET_COLOR := Color(1, 1, 0.75, 0.7)
## How far the label sits off the surface, towards the viewer, in metres.
const SURFACE_OFFSET := 0.015


func _init() -> void:
	billboard = BaseMaterial3D.BILLBOARD_ENABLED
	no_depth_test = true  # stay readable when the label is behind drawn geometry
	pixel_size = 0.0005
	outline_size = 12
	outline_modulate = Color(0, 0, 0, 0.85)
	set_live()


## Shows the length between two points, placed at their midpoint and lifted off the
## surface along `surface_normal`.
func show_length(from: Vector3, to: Vector3, surface_normal: Vector3) -> void:
	var new_text := "%d mm" % roundi(from.distance_to(to) * 1000.0)
	if new_text != text:
		text = new_text
	global_position = (from + to) / 2.0 + surface_normal * SURFACE_OFFSET
	visible = true


func set_live() -> void:
	font_size = LIVE_FONT_SIZE
	modulate = LIVE_COLOR


func set_committed() -> void:
	font_size = SET_FONT_SIZE
	modulate = SET_COLOR
