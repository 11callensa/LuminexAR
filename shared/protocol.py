"""UDP host and ports linking the Pi services to the Godot app.

The values live in protocol.json so Python, GDScript and the native services'
launch arguments all read the same numbers from one file.
"""

import json
from pathlib import Path

_PROTOCOL: dict = json.loads(Path(__file__).with_name("protocol.json").read_text())

HOST: str = _PROTOCOL["host"]


def port(name: str) -> int:
    """Return the UDP port for a named link, e.g. "stylus_state" (see protocol.json)."""
    return int(_PROTOCOL["ports"][name])
