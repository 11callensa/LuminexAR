extends Control

@export var metric_name: String = "SYS"
@export var bar_color_filled: Color = Color(0, 1, 0)
@export var bar_color_empty: Color = Color(1, 1, 1, 0.25)

var level: int = 3

@onready var name_label: Label = $NameLabel

func _ready():
	name_label.text = metric_name
	queue_redraw()

func set_level(new_level: int):
	level = clamp(new_level, 0, 3)
	queue_redraw()

func _draw():
	var bar_count = 3
	var bar_width = 6
	var spacing = 3
	var max_height = 28
	var base_y = 34

	for i in range(bar_count):
		var bar_height = max_height * float(i + 1) / bar_count
		var x = i * (bar_width + spacing)
		var y = base_y - bar_height
		var color = bar_color_filled if i < level else bar_color_empty
		draw_rect(Rect2(x, y, bar_width, bar_height), color)
