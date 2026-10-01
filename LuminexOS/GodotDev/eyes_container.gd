extends HBoxContainer

@export var left_3d: TextureRect
@export var right_3d: TextureRect
@export var left_ui: TextureRect
@export var right_ui: TextureRect
@export var left_viewport: SubViewport
@export var right_viewport: SubViewport
@export var ui_viewport: SubViewport

func _ready():
	for rect in [left_3d, right_3d, left_ui, right_ui]:
		rect.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		rect.stretch_mode = TextureRect.STRETCH_SCALE
		rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		rect.mouse_filter = Control.MOUSE_FILTER_IGNORE

	ui_viewport.transparent_bg = true

	left_3d.texture = left_viewport.get_texture()
	right_3d.texture = right_viewport.get_texture()
	left_ui.texture = ui_viewport.get_texture()
	right_ui.texture = ui_viewport.get_texture()
