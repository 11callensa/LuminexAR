"""Finds the RGB and depth cameras by identity instead of /dev/videoN number.

Linux numbers video devices in the order they appear, so the numbers change with
plug-in order. The identities live in cameras.json.
"""

import json
from pathlib import Path

_CAMERAS: dict = json.loads(Path(__file__).with_name("cameras.json").read_text())

V4L_BY_ID = Path("/dev/v4l/by-id")
V4L_SYSFS = Path("/sys/class/video4linux")


def rgb_camera_path() -> str:
    """Stable path to the USB RGB camera (udev's by-id link), whatever videoN it got."""
    return str(V4L_BY_ID / _CAMERAS["rgb_camera_by_id"])


def depth_camera_index() -> int:
    """videoN number of the ToF camera's main CSI channel, for ArducamCamera.open()."""
    name = _CAMERAS["depth_camera_node_name"]
    matches = [
        int(node.name.removeprefix("video"))
        for node in V4L_SYSFS.glob("video*")
        if (node / "name").read_text().strip() == name
    ]
    if not matches:
        raise RuntimeError(f"No video device named {name!r}; is the depth camera connected?")
    return min(matches)
