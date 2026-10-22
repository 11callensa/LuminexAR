class_name GlassesScreen

## Puts the app window fullscreen on the glasses rather than whichever monitor the
## desktop picked. Godot cannot read monitor names, so scripts/launch_glasses.sh finds
## the glasses by make and passes their desktop position as --glasses-position=X,Y.

const POSITION_ARG := "--glasses-position="


## Moves the window to the screen at the launcher-given position and makes it
## fullscreen. Does nothing when started without the launcher (e.g. from the editor).
static func move_window_to_glasses(window: Window) -> void:
	var target: Variant = _position_from_args()
	if target == null:
		return

	for screen in DisplayServer.get_screen_count():
		if DisplayServer.screen_get_position(screen) == target:
			window.mode = Window.MODE_WINDOWED
			window.current_screen = screen
			window.mode = Window.MODE_FULLSCREEN
			print("Fullscreen on glasses: screen ", screen, " at ", target)
			return

	var positions: Array[Vector2i] = []
	for screen in DisplayServer.get_screen_count():
		positions.append(DisplayServer.screen_get_position(screen))
	push_error("No screen at glasses position %s (screens at %s)" % [target, positions])


static func _position_from_args() -> Variant:
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with(POSITION_ARG):
			var xy := arg.trim_prefix(POSITION_ARG).split(",")
			if xy.size() == 2 and xy[0].is_valid_int() and xy[1].is_valid_int():
				return Vector2i(xy[0].to_int(), xy[1].to_int())
			push_error("Bad " + arg + " (expected X,Y)")
	return null
