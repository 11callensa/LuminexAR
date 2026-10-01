extends Node

@export var receiver: Node
@export var stylus_ray: Node
@export var head_anchor: Node3D

const MAX_PLANES = 3

var plane_meshes: Array[MeshInstance3D] = []
var normal_lines: Array[MeshInstance3D] = []
var edge_outlines: Array[MeshInstance3D] = []

var plane_colors: Array[Color] = [
	Color(1, 0.2, 0.2, 0.4),
	Color(0.2, 1, 0.2, 0.4),
	Color(0.2, 0.4, 1, 0.4)
]

var arrow_material: StandardMaterial3D
var outline_material: StandardMaterial3D

var cached_valid: Array[bool] = [false, false, false]
var cached_centroid: Array[Vector3] = [Vector3.ZERO, Vector3.ZERO, Vector3.ZERO]
var cached_normal: Array[Vector3] = [Vector3.ZERO, Vector3.ZERO, Vector3.ZERO]
var cached_right: Array[Vector3] = [Vector3.ZERO, Vector3.ZERO, Vector3.ZERO]
var cached_up: Array[Vector3] = [Vector3.ZERO, Vector3.ZERO, Vector3.ZERO]
var cached_points_2d: Array = [PackedVector2Array(), PackedVector2Array(), PackedVector2Array()]
var cached_corners_3d: Array = [[], [], []]

# once frozen, a plane stops updating from live UDP data entirely —
# these hold its permanent, fixed world-space geometry
var is_frozen: Array[bool] = [false, false, false]

var hovered_index: int = -1

signal plane_frozen


func _ready():
	arrow_material = StandardMaterial3D.new()
	arrow_material.albedo_color = Color(1, 1, 0)
	arrow_material.emission_enabled = true
	arrow_material.emission = Color(1, 1, 0)
	arrow_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED

	outline_material = StandardMaterial3D.new()
	outline_material.albedo_color = Color(1, 1, 0)
	outline_material.emission_enabled = true
	outline_material.emission = Color(1, 1, 0)
	outline_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED

	for i in range(MAX_PLANES):
		var plane_mi = MeshInstance3D.new()
		plane_mi.name = "Plane_" + str(i)
		plane_mi.visible = false
		add_child(plane_mi)
		plane_meshes.append(plane_mi)

		var line_mi = MeshInstance3D.new()
		line_mi.name = "Normal_" + str(i)
		line_mi.visible = false
		add_child(line_mi)
		normal_lines.append(line_mi)

		var outline_mi = MeshInstance3D.new()
		outline_mi.name = "Outline_" + str(i)
		outline_mi.visible = false
		add_child(outline_mi)
		edge_outlines.append(outline_mi)

	if receiver:
		receiver.planes_received.connect(_on_planes_received)


func _process(_delta):
	_update_hover_state()


func _convert_point(x: float, y: float, z: float) -> Vector3:
	return Vector3(x, -y, -z)


func _on_planes_received(planes: Array):
	for i in range(MAX_PLANES):
		if is_frozen[i]:
			continue  # frozen planes never take new data again

		if i < planes.size():
			_update_plane(i, planes[i])
		else:
			plane_meshes[i].visible = false
			normal_lines[i].visible = false
			edge_outlines[i].visible = false
			cached_valid[i] = false


func _update_plane(index: int, data: Dictionary):
	if not data.has("corners_flat") or data["corners_flat"].size() < 9:
		plane_meshes[index].visible = false
		normal_lines[index].visible = false
		edge_outlines[index].visible = false
		cached_valid[index] = false
		return

	var corners_flat = data["corners_flat"]
	var corner_count = corners_flat.size() / 3

	var corners: Array[Vector3] = []
	for c in range(corner_count):
		corners.append(_convert_point(
			corners_flat[c * 3 + 0],
			corners_flat[c * 3 + 1],
			corners_flat[c * 3 + 2]
		))

	var centroid = _convert_point(
		data["centroid"][0],
		data["centroid"][1],
		data["centroid"][2]
	)

	var normal = Vector3(
		data["normal"][0],
		-data["normal"][1],
		-data["normal"][2]
	).normalized()

	var arbitrary = Vector3(1, 0, 0) if abs(normal.x) < 0.9 else Vector3(0, 1, 0)
	var right = arbitrary.cross(normal).normalized()
	var up_in_plane = normal.cross(right).normalized()

	var points_2d := PackedVector2Array()
	for c in corners:
		var rel = c - centroid
		points_2d.append(Vector2(rel.dot(right), rel.dot(up_in_plane)))

	cached_valid[index] = true
	cached_centroid[index] = centroid
	cached_normal[index] = normal
	cached_right[index] = right
	cached_up[index] = up_in_plane
	cached_points_2d[index] = points_2d
	cached_corners_3d[index] = corners

	_build_plane_visuals(index, corners, centroid, normal, points_2d)


func _build_plane_visuals(index: int, corners: Array[Vector3], centroid: Vector3, normal: Vector3, points_2d: PackedVector2Array):
	var triangle_indices = Geometry2D.triangulate_polygon(points_2d)

	var st = SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)

	for i in range(0, triangle_indices.size(), 3):
		st.add_vertex(corners[triangle_indices[i]])
		st.add_vertex(corners[triangle_indices[i + 1]])
		st.add_vertex(corners[triangle_indices[i + 2]])

	st.generate_normals()

	var plane_mi = plane_meshes[index]
	plane_mi.mesh = st.commit()

	var plane_mat := StandardMaterial3D.new()
	plane_mat.albedo_color = plane_colors[index]
	plane_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	plane_mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	plane_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	plane_mi.material_override = plane_mat

	plane_mi.visible = true

	_build_normal_arrow(index, centroid, normal)
	_build_edge_outline(index, corners)


func _build_normal_arrow(index: int, centroid: Vector3, normal: Vector3):
	var arrow_length = 0.12
	var shaft_radius = 0.003
	var head_radius = 0.012
	var head_length = 0.03
	var shaft_length = arrow_length - head_length

	var arrow_up = normal
	var arrow_arbitrary = Vector3(1, 0, 0) if abs(arrow_up.x) < 0.9 else Vector3(0, 1, 0)
	var arrow_right = arrow_arbitrary.cross(arrow_up).normalized()
	var arrow_forward = arrow_up.cross(arrow_right).normalized()
	var arrow_basis = Basis(arrow_right, arrow_up, arrow_forward)

	var line_mi = normal_lines[index]

	for child in line_mi.get_children():
		child.queue_free()

	var shaft_mesh_instance = MeshInstance3D.new()
	var shaft = CylinderMesh.new()
	shaft.top_radius = shaft_radius
	shaft.bottom_radius = shaft_radius
	shaft.height = shaft_length
	shaft_mesh_instance.mesh = shaft
	shaft_mesh_instance.material_override = arrow_material
	line_mi.add_child(shaft_mesh_instance)
	shaft_mesh_instance.global_transform = Transform3D(
		arrow_basis,
		centroid + normal * (shaft_length / 2.0)
	)

	var head_mesh_instance = MeshInstance3D.new()
	var head = CylinderMesh.new()
	head.top_radius = 0.0
	head.bottom_radius = head_radius
	head.height = head_length
	head_mesh_instance.mesh = head
	head_mesh_instance.material_override = arrow_material
	line_mi.add_child(head_mesh_instance)
	head_mesh_instance.global_transform = Transform3D(
		arrow_basis,
		centroid + normal * (shaft_length + head_length / 2.0)
	)

	line_mi.visible = true


func _build_edge_outline(index: int, corners: Array[Vector3]):
	var outline_mi = edge_outlines[index]

	for child in outline_mi.get_children():
		child.queue_free()

	var outline_thickness = 0.004
	var corner_count = corners.size()

	for i in range(corner_count):
		var start = corners[i]
		var end = corners[(i + 1) % corner_count]

		var segment = end - start
		var length = segment.length()

		if length < 0.0001:
			continue

		var direction = segment.normalized()

		var up = direction
		var arbitrary = Vector3(1, 0, 0) if abs(up.x) < 0.9 else Vector3(0, 1, 0)
		var right = arbitrary.cross(up).normalized()
		var forward = up.cross(right).normalized()
		var segment_basis = Basis(right, up, forward)

		var segment_mesh_instance = MeshInstance3D.new()
		var cylinder = CylinderMesh.new()
		cylinder.top_radius = outline_thickness
		cylinder.bottom_radius = outline_thickness
		cylinder.height = length
		segment_mesh_instance.mesh = cylinder
		segment_mesh_instance.material_override = outline_material

		outline_mi.add_child(segment_mesh_instance)
		segment_mesh_instance.global_transform = Transform3D(
			segment_basis,
			start + direction * (length / 2.0)
		)


func _update_hover_state():
	if stylus_ray == null:
		return

	var origin = stylus_ray.get_ray_origin()
	var direction = stylus_ray.get_ray_direction()

	var closest_index = -1
	var closest_t = INF

	for i in range(MAX_PLANES):
		if not cached_valid[i] or is_frozen[i]:
			continue

		var denom = direction.dot(cached_normal[i])

		if abs(denom) < 0.0001:
			continue

		var t = (cached_centroid[i] - origin).dot(cached_normal[i]) / denom

		if t < 0:
			continue

		var hit_point = origin + direction * t

		var rel = hit_point - cached_centroid[i]
		var hit_2d = Vector2(rel.dot(cached_right[i]), rel.dot(cached_up[i]))

		if Geometry2D.is_point_in_polygon(hit_2d, cached_points_2d[i]):
			if t < closest_t:
				closest_t = t
				closest_index = i

	hovered_index = closest_index

	for i in range(MAX_PLANES):
		if is_frozen[i]:
			edge_outlines[i].visible = false
		else:
			edge_outlines[i].visible = cached_valid[i] and i == hovered_index


# Called externally (from GameManager) on mode button press.
# Returns true if a plane was actually frozen.
func try_freeze_hovered_plane() -> bool:
	if hovered_index == -1:
		return false

	if head_anchor == null:
		print("PlaneVisualizer: head_anchor not set, cannot freeze in world space")
		return false

	_freeze_plane(hovered_index)
	return true


func _freeze_plane(index: int):
	is_frozen[index] = true
	edge_outlines[index].visible = false

	_build_plane_visuals(
		index,
		cached_corners_3d[index],
		cached_centroid[index],
		cached_normal[index],
		cached_points_2d[index]
	)

	print("Plane ", index, " frozen")
	
	# clear every other slot — surface_visualiser is about to be killed,
	# so any other planes are now stale and must not remain hoverable
	for i in range(MAX_PLANES):
		if i != index:
			cached_valid[i] = false
			plane_meshes[i].visible = false
			normal_lines[i].visible = false
			edge_outlines[i].visible = false

	emit_signal("plane_frozen")


func reset_all_planes():
	for i in range(MAX_PLANES):
		is_frozen[i] = false
		cached_valid[i] = false
		plane_meshes[i].visible = false
		normal_lines[i].visible = false
		edge_outlines[i].visible = false


func get_frozen_plane_index() -> int:
	for i in range(MAX_PLANES):
		if is_frozen[i]:
			return i
	return -1


func get_plane_frame(index: int) -> Dictionary:
	return {
		"centroid": cached_centroid[index],
		"normal": cached_normal[index],
		"right": cached_right[index],
		"up": cached_up[index]
	}
