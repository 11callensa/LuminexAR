"""Reads the Intel RealSense R200's colour and depth streams through Linux V4L2.

Experimental: evaluating the R200 as a single-module replacement for the Arducam ToF
and USB RGB cameras. Intel's current RealSense SDK dropped the R200, but the camera is a
standard UVC device, so OpenCV reads it directly with no extra dependencies.
"""

from pathlib import Path

import cv2
import numpy as np

V4L_SYSFS = Path("/sys/class/video4linux")
R200_NAME = "Intel RealSense 3D Camera R200"

# All six R200 video nodes share one name and their /dev/videoN numbers depend on plug-in
# order, but each stream sits on a fixed USB interface of the camera.
STREAM_INTERFACES = {"depth": "1.2", "colour": "1.4"}

DEPTH_SIZE = (628, 469)
COLOUR_SIZE = (640, 480)
FPS = 30


def find_devices() -> dict[str, str]:
    """Maps "depth" and "colour" to their /dev/videoN paths."""
    devices: dict[str, str] = {}
    for node in V4L_SYSFS.glob("video*"):
        if not (node / "name").read_text().startswith(R200_NAME):
            continue
        interface = (node / "device").resolve().name.rsplit(":", 1)[-1]
        for stream, stream_interface in STREAM_INTERFACES.items():
            if interface == stream_interface:
                devices[stream] = f"/dev/{node.name}"
    missing = set(STREAM_INTERFACES) - set(devices)
    if missing:
        raise RuntimeError(f"R200 {', '.join(sorted(missing))} stream not found; is the camera plugged in?")
    return devices


def _open(device: str, fourcc: str, size: tuple[int, int], fps: int, raw: bool) -> cv2.VideoCapture:
    capture = cv2.VideoCapture(device, cv2.CAP_V4L2)
    capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, size[0])
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, size[1])
    capture.set(cv2.CAP_PROP_FPS, fps)
    if raw:
        # OpenCV cannot convert Z16 depth to colour; hand back the raw bytes instead.
        capture.set(cv2.CAP_PROP_CONVERT_RGB, 0)
    if not capture.isOpened():
        raise RuntimeError(f"Could not open {device} as {fourcc.strip()} {size[0]}x{size[1]}")
    return capture


class R200:
    """The R200's colour (BGR) and depth (uint16 millimetres, 0 = no reading) streams."""

    def __init__(self, colour_size: tuple[int, int] = COLOUR_SIZE,
                 depth_size: tuple[int, int] = DEPTH_SIZE, fps: int = FPS) -> None:
        devices = find_devices()
        self.depth_size = depth_size
        self._colour = _open(devices["colour"], "YUYV", colour_size, fps, raw=False)
        self._depth = _open(devices["depth"], "Z16 ", depth_size, fps, raw=True)

    def read_colour(self) -> np.ndarray | None:
        ok, frame = self._colour.read()
        return frame if ok else None

    def read_depth(self) -> np.ndarray | None:
        ok, raw = self._depth.read()
        if not ok:
            return None
        width, height = self.depth_size
        return raw.view(np.uint16).reshape(height, width)

    def close(self) -> None:
        self._colour.release()
        self._depth.release()

    def __enter__(self) -> "R200":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
