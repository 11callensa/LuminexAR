class_name Repo

## Locates the Luminex repo root, which holds the services, the .venv and shared/.

static var _root: String = ""


## Absolute path of the repo root, found once and cached.
static func root() -> String:
	if _root == "":
		_root = _find_root()
	return _root


static func _find_root() -> String:
	# Editor: start from the project folder. Exported game: start from the executable's folder.
	var dir: String
	if OS.has_feature("editor"):
		dir = ProjectSettings.globalize_path("res://")
	else:
		dir = OS.get_executable_path().get_base_dir()
	dir = dir.rstrip("/")
	while dir != "" and dir != "/":
		if FileAccess.file_exists(dir.path_join(".gitmodules")):
			return dir
		dir = dir.get_base_dir()
	push_error("Could not find the Luminex repo root (no .gitmodules above " + dir + ")")
	return ""
