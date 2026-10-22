class_name Protocol

## UDP host and ports shared with the Pi services, read from shared/protocol.json
## so the app and the services can never disagree on a port.

static var _data: Dictionary = {}


## Host every service sends to (and the native services are told to send to).
static func host() -> String:
	return _load().get("host", "")


## UDP port for a named link, e.g. "planes"; -1 (and an error) if it is missing.
static func port(link_name: String) -> int:
	var ports: Dictionary = _load().get("ports", {})
	if not ports.has(link_name):
		push_error("No port named '" + link_name + "' in shared/protocol.json")
		return -1
	return int(ports[link_name])


static func _load() -> Dictionary:
	if _data.is_empty():
		var path := Repo.root().path_join("shared/protocol.json")
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
		if parsed is Dictionary:
			_data = parsed
		else:
			push_error("Could not read " + path)
	return _data
