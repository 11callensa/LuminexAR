extends Node

@export var loading_panel: Control
@export var calibration_panel: Control
@export var plane_selection_panel: Control
@export var workspace: Node3D
@export var stylus: Node3D
@export var sensor_calibration_panel: Control
@export var udp_receiver: Node

@export var glasses_calibration_panel: Control
@export var head_anchor: Node
@export var plane_visualiser: Node
@export var plane_drawing_controller: Node

@export var stylus_ray: Node

@export var calibration_enabled: bool = false
@export var show_debug_stylus_in_plane_selection: bool = true

@export var fade_duration: float = 0.01
@export var calibration_hold_time: float = 1.0

var _connected: bool = false

const PYTHON_EXECUTABLE = "/home/alex/Documents/Luminex/.venv/bin/python3"
const STYLUS_SCRIPTS_DIR = "/home/alex/Documents/Luminex/LuminexScripts/Stylus/"
const DEPTH_CAMERA_SCRIPTS_DIR = "/home/alex/Documents/Luminex/LuminexScripts/Depth_Camera/OG_depth"
const HEAD_TRACKER_EXECUTABLE = "/home/alex/Documents/Luminex/nrealAirLinuxDriver/build/examples/head_tracker/xrealAirHeadTracker"

var stylus_receiver_pid: int = -1
var stylus_tracker_pid: int = -1
var surface_visualiser_pid: int = -1
var head_tracker_pid: int = -1


func _launch_script(script_path: String) -> int:
	var pid = OS.create_process(
		PYTHON_EXECUTABLE,
		[script_path],
		false
	)

	if pid == -1:
		print("Failed to launch ", script_path)
	else:
		print("Launched ", script_path, " (pid ", pid, ")")

	return pid


func _launch_native_process(executable_path: String) -> int:
	var pid = OS.create_process(executable_path, [], false)

	if pid == -1:
		print("Failed to launch ", executable_path)
	else:
		print("Launched ", executable_path, " (pid ", pid, ")")

	return pid


func _kill_process(pid: int, force: bool = true) -> void:
	if pid == -1:
		return

	if force:
		OS.execute("kill", ["-9", str(pid)])
	else:
		OS.execute("kill", ["-15", str(pid)])


func _ready():
	stylus_receiver_pid = _launch_script(STYLUS_SCRIPTS_DIR + "stylus_receiver.py")
	head_tracker_pid = _launch_native_process(HEAD_TRACKER_EXECUTABLE)

	loading_panel.visible = true
	loading_panel.modulate.a = 1.0
	calibration_panel.visible = false
	plane_selection_panel.visible = false
	stylus_ray.set_ray_visible(false)

	sensor_calibration_panel.visible = false
	glasses_calibration_panel.visible = false        # ADD THIS LINE

	udp_receiver.state_received.connect(_on_state_received)
	stylus.calibrated.connect(_on_calibrated)
	plane_visualiser.plane_frozen.connect(_on_plane_frozen)
	
	workspace.visible = false

	get_tree().root.close_requested.connect(_on_app_closing)


func _on_state_received(rotation: Quaternion, wheel: int, wheel_click: bool, mode_button: bool):
	if mode_button and sensor_calibration_panel.visible:
		if sensor_calibration_panel.is_ready_to_proceed():
			sensor_calibration_panel.visible = false

			calibration_panel.visible = true
			calibration_panel.modulate.a = 1.0
			calibration_panel.mouse_filter = Control.MOUSE_FILTER_STOP

	if wheel_click and calibration_panel.visible:
		stylus.calibrate()
	
	if mode_button and glasses_calibration_panel.visible:
		head_anchor.calibrate_head()
		glasses_calibration_panel.visible = false
		_enter_plane_selection()
	
	if mode_button and plane_selection_panel.visible:
		print("Mode button pressed. hovered_index=", plane_visualiser.hovered_index, " plane_initialized=", plane_drawing_controller.plane_initialized)
		if plane_visualiser.hovered_index != -1:
			if plane_visualiser.try_freeze_hovered_plane():
				print("Plane freeze triggered")
		else:
			plane_drawing_controller.handle_point_action()
	
	if plane_selection_panel.visible and plane_drawing_controller.is_shape_enclosed():
		plane_drawing_controller.update_extrusion(wheel)

	if wheel_click and plane_drawing_controller.is_shape_enclosed():
		plane_drawing_controller.finalize_extrusion()
	


func _on_stylus_connected():
	print("Entering sensor calibration")

	_connected = true

	loading_panel.visible = false
	workspace.visible = true
	stylus.visible = true

	if calibration_enabled:
		sensor_calibration_panel.visible = true
	else:
		_enter_plane_selection()


func _enter_plane_selection():
	stylus_tracker_pid = _launch_script(STYLUS_SCRIPTS_DIR + "stylus_tracker.py")
	surface_visualiser_pid = _launch_script(DEPTH_CAMERA_SCRIPTS_DIR + "surface_visualiser.py")
	#stylus.visible = show_debug_stylus_in_plane_selection
	stylus.visible = false
	stylus_ray.set_ray_visible(true)

	plane_selection_panel.visible = true
	plane_selection_panel.modulate.a = 0.0
	await _fade_control(plane_selection_panel, 0.0, 1.0)


func _on_calibrated():
	print("Calibration finished")
	_calibration_finished_sequence()


func _calibration_finished_sequence():
	await get_tree().create_timer(calibration_hold_time).timeout

	if not _connected:
		return

	await _fade_control(calibration_panel, 1.0, 0.0)

	if not _connected:
		return

	calibration_panel.visible = false

	glasses_calibration_panel.visible = true


func _fade_control(control: Control, from_alpha: float, to_alpha: float) -> void:
	control.mouse_filter = Control.MOUSE_FILTER_IGNORE

	var tween = create_tween()
	tween.tween_property(control, "modulate:a", to_alpha, fade_duration).from(from_alpha)

	await tween.finished

	var visible_now = to_alpha > 0.0
	control.mouse_filter = Control.MOUSE_FILTER_STOP if visible_now else Control.MOUSE_FILTER_IGNORE


func _on_stylus_disconnected():
	print("Stylus Disconnected")

	_connected = false

	workspace.visible = false
	stylus.visible = false
	stylus_ray.set_ray_visible(false)

	sensor_calibration_panel.visible = false
	glasses_calibration_panel.visible = false

	calibration_panel.visible = false
	calibration_panel.modulate.a = 1.0

	plane_selection_panel.visible = false
	plane_selection_panel.modulate.a = 1.0

	loading_panel.visible = true
	loading_panel.modulate.a = 1.0

	_kill_process(stylus_tracker_pid)
	_kill_process(surface_visualiser_pid)
	stylus_tracker_pid = -1
	surface_visualiser_pid = -1

	if stylus.has_method("reset_calibration"):
		stylus.reset_calibration()

	if head_anchor.has_method("reset_head_calibration"):
		head_anchor.reset_head_calibration()
		

func _on_app_closing():
	_kill_process(stylus_receiver_pid, false)
	_kill_process(stylus_tracker_pid)
	_kill_process(surface_visualiser_pid)
	_kill_process(head_tracker_pid)
	get_tree().quit()


func _on_plane_frozen():
	print("Plane frozen — stopping surface_visualiser.py")
	_kill_process(surface_visualiser_pid, true)
	surface_visualiser_pid = -1
