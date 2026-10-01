extends Node

@export var stylus: Node3D
@export var ray_color: Color = Color(0, 1, 0)
@export var ray_length: float = 2.0
@export var ray_thickness: float = 0.005

# Which local axis of Stylus points out through the tip.
@export var forward_axis_local: Vector3 = Vector3(0, 0, -1)

var mesh_instance: MeshInstance3D

func _ready():
	mesh_instance = MeshInstance3D.new()
	add_child(mesh_instance)

	var cylinder := CylinderMesh.new()
	cylinder.top_radius = ray_thickness
	cylinder.bottom_radius = ray_thickness
	cylinder.height = ray_length
	mesh_instance.mesh = cylinder

	var material := StandardMaterial3D.new()
	material.albedo_color = ray_color
	material.emission_enabled = true
	material.emission = ray_color
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mesh_instance.material_override = material


func _process(_delta):
	if stylus == null:
		return

	var origin = stylus.global_transform.origin
	var direction = (stylus.global_transform.basis * forward_axis_local).normalized()

	# CylinderMesh's default orientation points along +Y, so we need a
	# basis whose Y axis aligns with our direction vector.
	var up = direction
	var arbitrary = Vector3(1, 0, 0) if abs(up.x) < 0.9 else Vector3(0, 1, 0)
	var right = arbitrary.cross(up).normalized()
	var forward = up.cross(right).normalized()

	var new_basis = Basis(right, up, forward)

	# midpoint, since CylinderMesh is centered on its own origin,
	# not anchored at one end
	var midpoint = origin + direction * (ray_length / 2.0)

	mesh_instance.global_transform = Transform3D(new_basis, midpoint)


func set_ray_visible(is_visible: bool):
	mesh_instance.visible = is_visible


func get_ray_origin() -> Vector3:
	if stylus == null:
		return Vector3.ZERO
	return stylus.global_transform.origin


func get_ray_direction() -> Vector3:
	if stylus == null:
		return Vector3.ZERO
	return (stylus.global_transform.basis * forward_axis_local).normalized()
