extends Node

@export var plane_visualiser: Node
@export var stylus_ray: Node

@export var lock_on_radius: float = 0.02
@export var point_marker_radius: float = 0.006
@export var line_thickness: float = 0.003
@export var extrusion_sensitivity: float = 0.002

var plane_index: int = -1
var plane_centroid: Vector3
var plane_normal: Vector3
var plane_right: Vector3
var plane_up: Vector3
var plane_initialized := false

var points: Array[Vector3] = []
var point_marker_nodes: Array[MeshInstance3D] = []
var line_nodes: Array[MeshInstance3D] = []
var preview_line_node: MeshInstance3D
var cursor_marker_node: MeshInstance3D

var is_enclosed := false
var fill_node: MeshInstance3D
var extrusion_node: MeshInstance3D
var is_extruding := false
var is_extrusion_finalized := false
var extrusion_depth := 0.0

var points_2d_cache: PackedVector2Array
var triangle_indices_cache: PackedInt32Array

var point_material: StandardMaterial3D
var line_material: StandardMaterial3D
var fill_material: ShaderMaterial

var extrusion_material: StandardMaterial3D
var extrusion_edge_material: StandardMaterial3D
var extrusion_outline_node: MeshInstance3D


func _ready():
	point_material = _make_unshaded_material(Color(1, 1, 0, 0.85))
	line_material = _make_unshaded_material(Color(1, 1, 0, 0.85))
	fill_material = _make_stripe_shader_material()
	extrusion_material = _make_unshaded_material(Color(0, 0.4, 1, 0.6))
	extrusion_edge_material = _make_unshaded_material(Color(1, 1, 0, 0.9))

	preview_line_node = MeshInstance3D.new()
	add_child(preview_line_node)
	preview_line_node.visible = false

	cursor_marker_node = MeshInstance3D.new()
	add_child(cursor_marker_node)
	cursor_marker_node.visible = false

	extrusion_outline_node = MeshInstance3D.new()
	add_child(extrusion_outline_node)


func _make_unshaded_material(color: Color) -> StandardMaterial3D:
	var mat = StandardMaterial3D.new()
	mat.albedo_color = color
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	mat.emission_enabled = true
	mat.emission = color
	return mat


func _make_stripe_shader_material() -> ShaderMaterial:
	var shader = Shader.new()
	shader.code = """
shader_type spatial;
render_mode unshaded, cull_disabled, blend_mix, depth_draw_always;

uniform vec4 color_a : source_color = vec4(0.0, 0.4, 1.0, 0.5);
uniform vec4 color_b : source_color = vec4(0.0, 0.0, 0.0, 0.5);
uniform float stripe_width = 0.02;

void fragment() {
	float diag = (UV.x + UV.y) / stripe_width;
	float stripe = mod(floor(diag), 2.0);
	ALBEDO = mix(color_a.rgb, color_b.rgb, stripe);
	ALPHA = mix(color_a.a, color_b.a, stripe);
}
"""
	var mat = ShaderMaterial.new()
	mat.shader = shader
	return mat


func _process(_delta):
	if not plane_initialized:
		_try_activate()
		return

	if is_enclosed:
		preview_line_node.visible = false
		cursor_marker_node.visible = false
		return

	var cursor = _get_plane_cursor()

	if cursor == null:
		preview_line_node.visible = false
		cursor_marker_node.visible = false
		return

	var snapped = _apply_lock_on(cursor)

	cursor_marker_node.visible = true
	_update_cursor_marker(snapped)

	if points.size() > 0:
		preview_line_node.visible = true
		_update_line_mesh(preview_line_node, points[points.size() - 1], snapped, line_material, line_thickness)
	else:
		preview_line_node.visible = false


func _try_activate():
	if plane_visualiser == null:
		return

	var idx = plane_visualiser.get_frozen_plane_index()

	if idx == -1:
		return

	var frame = plane_visualiser.get_plane_frame(idx)
	plane_index = idx
	plane_centroid = frame["centroid"]
	plane_normal = frame["normal"]
	plane_right = frame["right"]
	plane_up = frame["up"]
	plane_initialized = true

	print("Drawing activated on frozen plane ", idx)


func _get_plane_cursor():
	if stylus_ray == null:
		return null

	var origin = stylus_ray.get_ray_origin()
	var direction = stylus_ray.get_ray_direction()

	var denom = direction.dot(plane_normal)

	if abs(denom) < 0.0001:
		return null

	var t = (plane_centroid - origin).dot(plane_normal) / denom

	if t < 0:
		return null

	return origin + direction * t


func _apply_lock_on(cursor: Vector3) -> Vector3:
	if points.size() < 3:
		return cursor

	var first = points[0]

	if cursor.distance_to(first) < lock_on_radius:
		return first

	return cursor


# Called from GameManager on a mode-button press, while drawing is active
func handle_point_action():
	if not plane_initialized or is_enclosed:
		return

	var cursor = _get_plane_cursor()

	if cursor == null:
		return

	var snapped = _apply_lock_on(cursor)

	if points.size() >= 3 and snapped.distance_to(points[0]) < 0.0001:
		_add_committed_line(points[points.size() - 1], points[0])
		_enclose_shape()
		return

	if points.size() > 0:
		_add_committed_line(points[points.size() - 1], snapped)

	_add_point_marker(snapped)
	points.append(snapped)


func _add_point_marker(pos: Vector3):
	var mi = MeshInstance3D.new()
	var sphere = SphereMesh.new()
	sphere.radius = point_marker_radius
	sphere.height = point_marker_radius * 2.0
	mi.mesh = sphere
	mi.material_override = point_material
	add_child(mi)
	mi.global_transform = Transform3D(Basis(), pos)
	point_marker_nodes.append(mi)


func _add_committed_line(from: Vector3, to: Vector3):
	var mi = MeshInstance3D.new()
	add_child(mi)
	_update_line_mesh(mi, from, to, line_material, line_thickness)
	line_nodes.append(mi)


func _update_line_mesh(mi: MeshInstance3D, from: Vector3, to: Vector3, material: Material, thickness: float):
	var segment = to - from
	var length = segment.length()

	if length < 0.0001:
		mi.visible = false
		return

	mi.visible = true

	var direction = segment.normalized()
	var up = direction
	var arbitrary = Vector3(1, 0, 0) if abs(up.x) < 0.9 else Vector3(0, 1, 0)
	var right = arbitrary.cross(up).normalized()
	var forward = up.cross(right).normalized()
	var basis = Basis(right, up, forward)

	var cylinder = CylinderMesh.new()
	cylinder.top_radius = thickness
	cylinder.bottom_radius = thickness
	cylinder.height = length
	mi.mesh = cylinder
	mi.material_override = material

	mi.global_transform = Transform3D(basis, from + direction * (length / 2.0))


func _update_cursor_marker(pos: Vector3):
	var sphere = SphereMesh.new()
	sphere.radius = point_marker_radius * 0.8
	sphere.height = point_marker_radius * 1.6
	cursor_marker_node.mesh = sphere
	cursor_marker_node.material_override = point_material
	cursor_marker_node.global_transform = Transform3D(Basis(), pos)


func _enclose_shape():
	is_enclosed = true
	preview_line_node.visible = false
	cursor_marker_node.visible = false

	points_2d_cache = PackedVector2Array()
	for p in points:
		var rel = p - plane_centroid
		points_2d_cache.append(Vector2(rel.dot(plane_right), rel.dot(plane_up)))

	triangle_indices_cache = Geometry2D.triangulate_polygon(points_2d_cache)

	var st = SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)

	for i in range(0, triangle_indices_cache.size(), 3):
		var ia = triangle_indices_cache[i]
		var ib = triangle_indices_cache[i + 1]
		var ic = triangle_indices_cache[i + 2]

		st.set_uv(points_2d_cache[ia])
		st.add_vertex(points[ia])
		st.set_uv(points_2d_cache[ib])
		st.add_vertex(points[ib])
		st.set_uv(points_2d_cache[ic])
		st.add_vertex(points[ic])

	st.generate_normals()

	fill_node = MeshInstance3D.new()
	fill_node.mesh = st.commit()
	fill_node.material_override = fill_material
	add_child(fill_node)

	print("Shape enclosed with ", points.size(), " points")


func is_shape_enclosed() -> bool:
	return is_enclosed and not is_extrusion_finalized


# Called from GameManager every state_received while enclosed and not finalized
func update_extrusion(wheel_delta: int):
	if not is_enclosed or is_extrusion_finalized:
		return

	if wheel_delta == 0:
		return

	is_extruding = true
	fill_node.visible = false

	extrusion_depth += wheel_delta * extrusion_sensitivity
	extrusion_depth = max(extrusion_depth, 0.0)

	_rebuild_extrusion_mesh()


func _rebuild_extrusion_mesh():
	if extrusion_node == null:
		extrusion_node = MeshInstance3D.new()
		add_child(extrusion_node)

	extrusion_node.material_override = extrusion_material

	var offset = plane_normal * extrusion_depth

	var st = SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)

	for i in range(0, triangle_indices_cache.size(), 3):
		var ia = triangle_indices_cache[i]
		var ib = triangle_indices_cache[i + 1]
		var ic = triangle_indices_cache[i + 2]

		st.add_vertex(points[ia] + offset)
		st.add_vertex(points[ib] + offset)
		st.add_vertex(points[ic] + offset)

	var point_count = points.size()
	for i in range(point_count):
		var a = points[i]
		var b = points[(i + 1) % point_count]
		var a_top = a + offset
		var b_top = b + offset

		st.add_vertex(a)
		st.add_vertex(b)
		st.add_vertex(b_top)

		st.add_vertex(a)
		st.add_vertex(b_top)
		st.add_vertex(a_top)

	st.generate_normals()

	extrusion_node.mesh = st.commit()

	_rebuild_extrusion_edges(offset)


func _rebuild_extrusion_edges(offset: Vector3):
	for child in extrusion_outline_node.get_children():
		child.queue_free()

	var point_count = points.size()

	for i in range(point_count):
		var a = points[i]
		var b = points[(i + 1) % point_count]

		_add_edge_segment(a, b, line_thickness)
		_add_edge_segment(a + offset, b + offset, line_thickness)
		_add_edge_segment(a, a + offset, line_thickness)


func _add_edge_segment(from: Vector3, to: Vector3, thickness: float):
	var segment = to - from
	var length = segment.length()

	if length < 0.0001:
		return

	var direction = segment.normalized()
	var up = direction
	var arbitrary = Vector3(1, 0, 0) if abs(up.x) < 0.9 else Vector3(0, 1, 0)
	var right = arbitrary.cross(up).normalized()
	var forward = up.cross(right).normalized()
	var basis = Basis(right, up, forward)

	var mi = MeshInstance3D.new()
	var cylinder = CylinderMesh.new()
	cylinder.top_radius = thickness
	cylinder.bottom_radius = thickness
	cylinder.height = length
	mi.mesh = cylinder
	mi.material_override = extrusion_edge_material

	extrusion_outline_node.add_child(mi)
	mi.global_transform = Transform3D(basis, from + direction * (length / 2.0))


func finalize_extrusion():
	if not is_extruding:
		return

	is_extrusion_finalized = true
	print("Extrusion finalized at depth ", extrusion_depth)
