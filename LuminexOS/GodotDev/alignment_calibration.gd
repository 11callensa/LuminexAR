class_name AlignmentCalibration
extends Node

## Calibration mode ("Luminex Calibrate"). With live planes and the stylus in view, the
## user tunes how the camera lines up with their eyes until virtual surfaces sit on the
## real ones, then saves it for every later launch.
##   Stylus:   scroll = adjust the highlighted setting, mode button = next setting,
##             wheel click = save.
##   Keyboard: Up/Down = select, Left/Right = adjust (Shift = 10x), Enter = save.

signal saved

const SETTINGS := [
	{"label": "Zoom (FOV)", "key": "eye_fov", "step": 0.1, "unit": "°", "min": 10.0, "max": 90.0},
	{"label": "Horizontal angle", "key": "yaw", "step": 0.1, "unit": "°", "min": -30.0, "max": 30.0},
	{"label": "Vertical angle", "key": "pitch", "step": 0.1, "unit": "°", "min": -30.0, "max": 30.0},
	{"label": "Tilt", "key": "roll", "step": 0.1, "unit": "°", "min": -30.0, "max": 30.0},
	{"label": "Camera offset X (right)", "key": "offset_x", "step": 0.001, "unit": "mm", "min": -0.2, "max": 0.2},
	{"label": "Camera offset Y (up)", "key": "offset_y", "step": 0.001, "unit": "mm", "min": -0.2, "max": 0.2},
	{"label": "Camera offset Z (back)", "key": "offset_z", "step": 0.001, "unit": "mm", "min": -0.2, "max": 0.2},
]
const FONT_SIZE := 30
const SELECTED_COLOR := Color(1, 0.85, 0.1)
const NORMAL_COLOR := Color(1, 1, 1, 0.85)
const SAVED_MESSAGE_SECONDS := 1.5

var head_anchor: Node3D
var _index := 0
var _panel: PanelContainer
var _rows: Array[Label] = []
var _hint: Label


## Shows the panel on the head-locked UI layer and starts taking input.
func start(anchor: Node3D, ui_root: Node) -> void:
	head_anchor = anchor
	_build_panel(ui_root)
	_refresh()


func is_active() -> bool:
	return _panel != null and _panel.visible


func handle_stylus(wheel: int, wheel_click: bool, mode_button: bool) -> void:
	if wheel != 0:
		_adjust(wheel)
	if mode_button:
		_index = (_index + 1) % SETTINGS.size()
		_refresh()
	if wheel_click:
		_save()


func _unhandled_key_input(event: InputEvent) -> void:
	if not is_active() or not (event is InputEventKey and event.pressed):
		return
	var ticks := 10 if event.shift_pressed else 1
	match event.physical_keycode:
		KEY_UP:
			_index = posmod(_index - 1, SETTINGS.size())
			_refresh()
		KEY_DOWN:
			_index = (_index + 1) % SETTINGS.size()
			_refresh()
		KEY_LEFT:
			_adjust(-ticks)
		KEY_RIGHT:
			_adjust(ticks)
		KEY_ENTER, KEY_KP_ENTER:
			_save()


func _adjust(ticks: int) -> void:
	var setting: Dictionary = SETTINGS[_index]
	var value: float = _get_value(setting["key"]) + ticks * setting["step"]
	value = clampf(snappedf(value, setting["step"]), setting["min"], setting["max"])
	_set_value(setting["key"], value)
	head_anchor.apply_calibration()
	_refresh()


func _save() -> void:
	if not head_anchor.calibration.save():
		_hint.text = "Could not save — see logs/glasses.log"
		return
	print("Alignment saved: ", _summary())
	_hint.text = "Saved ✓"
	await get_tree().create_timer(SAVED_MESSAGE_SECONDS).timeout
	_panel.visible = false
	saved.emit()


func _get_value(key: String) -> float:
	var calibration: GlassesCalibration = head_anchor.calibration
	match key:
		"offset_x": return calibration.camera_offset.x
		"offset_y": return calibration.camera_offset.y
		"offset_z": return calibration.camera_offset.z
	return calibration.get(key)


func _set_value(key: String, value: float) -> void:
	var calibration: GlassesCalibration = head_anchor.calibration
	match key:
		"offset_x": calibration.camera_offset.x = value
		"offset_y": calibration.camera_offset.y = value
		"offset_z": calibration.camera_offset.z = value
		_: calibration.set(key, value)


func _format(setting: Dictionary) -> String:
	var value := _get_value(setting["key"])
	if setting["unit"] == "mm":
		return "%d mm" % roundi(value * 1000.0)
	return "%.1f°" % value


func _summary() -> String:
	var parts := PackedStringArray()
	for setting in SETTINGS:
		parts.append("%s %s" % [setting["label"], _format(setting)])
	return ", ".join(parts)


func _refresh() -> void:
	for i in SETTINGS.size():
		var selected := i == _index
		_rows[i].text = ("▶ " if selected else "   ") + "%s   %s" % [SETTINGS[i]["label"], _format(SETTINGS[i])]
		_rows[i].add_theme_color_override("font_color", SELECTED_COLOR if selected else NORMAL_COLOR)


func _build_panel(ui_root: Node) -> void:
	_panel = PanelContainer.new()
	_panel.position = Vector2(60, 60)
	var box := VBoxContainer.new()
	_panel.add_child(box)

	var title := _make_label("Glasses alignment — line the planes up with the real surfaces")
	box.add_child(title)
	for i in SETTINGS.size():
		var row := _make_label("")
		box.add_child(row)
		_rows.append(row)
	_hint = _make_label("Scroll: adjust   ·   Mode button: next   ·   Click wheel: save")
	box.add_child(_hint)

	ui_root.add_child(_panel)


func _make_label(text: String) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", FONT_SIZE)
	label.add_theme_constant_override("outline_size", 6)
	label.add_theme_color_override("font_outline_color", Color.BLACK)
	return label
