extends Node3D

@export var left_eye_camera: Camera3D
@export var right_eye_camera: Camera3D
@export var left_viewport: SubViewport
@export var right_viewport: SubViewport
@export var ipd: float = 0.063
@export var head_orientation_receiver: Node
@export var ui_viewport: SubViewport

var head_calibration_offset := Quaternion.IDENTITY
var head_tracking_enabled := false
var last_raw_orientation := Quaternion.IDENTITY

var mirror_window: Window


func _ready():
	var shared_world = get_viewport().world_3d
	left_viewport.world_3d = shared_world
	right_viewport.world_3d = shared_world

	left_eye_camera.current = true
	right_eye_camera.current = true

	if head_orientation_receiver:
		head_orientation_receiver.head_orientation_received.connect(_on_head_orientation_received)

	_setup_mirror_window()


func _setup_mirror_window():
	mirror_window = Window.new()
	mirror_window.title = "Demo Mirror"
	mirror_window.size = Vector2i(1920, 1080)
	mirror_window.position = Vector2i(0, 0)
	mirror_window.borderless = false
	add_child(mirror_window)

	var mirror_3d_rect = TextureRect.new()
	mirror_3d_rect.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mirror_3d_rect.stretch_mode = TextureRect.STRETCH_SCALE
	mirror_3d_rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	mirror_window.add_child(mirror_3d_rect)
	mirror_3d_rect.texture = left_viewport.get_texture()

	var mirror_ui_rect = TextureRect.new()
	mirror_ui_rect.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mirror_ui_rect.stretch_mode = TextureRect.STRETCH_SCALE
	mirror_ui_rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	mirror_window.add_child(mirror_ui_rect)
	mirror_ui_rect.texture = ui_viewport.get_texture()

	mirror_window.show()


func _on_head_orientation_received(new_orientation: Quaternion):
	if not (
		is_finite(new_orientation.x)
		and is_finite(new_orientation.y)
		and is_finite(new_orientation.z)
		and is_finite(new_orientation.w)
	):
		return

	if new_orientation.length_squared() < 0.0001:
		return

	var remapped = Quaternion(
		new_orientation.y,
		-new_orientation.z,
		-new_orientation.x,
		new_orientation.w
	)

	last_raw_orientation = remapped

	if head_tracking_enabled:
		quaternion = head_calibration_offset * remapped


func calibrate_head():
	head_calibration_offset = last_raw_orientation.inverse()
	head_tracking_enabled = true
	print("Head calibrated")


func reset_head_calibration():
	head_calibration_offset = Quaternion.IDENTITY
	head_tracking_enabled = false


var _debug_timer := 0.0

func _process(_delta):
	var half_ipd = ipd / 2.0
	left_eye_camera.global_transform = global_transform * Transform3D(Basis(), Vector3(-half_ipd, 0, 0))
	right_eye_camera.global_transform = global_transform * Transform3D(Basis(), Vector3(half_ipd, 0, 0))

	_debug_timer += _delta
	if _debug_timer > 1.0:
		_debug_timer = 0.0
		print("HeadAnchor quat: ", quaternion, " tracking_enabled: ", head_tracking_enabled)
