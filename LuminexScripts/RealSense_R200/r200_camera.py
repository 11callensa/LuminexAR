"""Reads the Intel RealSense R200's colour and depth streams through Linux V4L2.

Experimental: evaluating the R200 as a single-module replacement for the Arducam ToF
and USB RGB cameras. Intel's current RealSense SDK dropped the R200, but the camera is a
standard UVC device, so OpenCV reads it directly with no extra dependencies.
"""

import ctypes
import fcntl
import os
from pathlib import Path

import cv2
import numpy as np

V4L_SYSFS = Path("/sys/class/video4linux")
R200_NAME = "Intel RealSense 3D Camera R200"

# All six R200 video nodes share one name and their /dev/videoN numbers depend on plug-in
# order, but each stream sits on a fixed USB interface of the camera.
STREAM_INTERFACES = {"infrared": "1.0", "depth": "1.2", "colour": "1.4"}

DEPTH_SIZE = (628, 469)
COLOUR_SIZE = (640, 480)
FPS = 30

# Depth settings are vendor controls on the camera's extension unit (GUID
# 18682d34-dd2c-4073-ad23-7214739a074c), reached through the infrared stream's node.
# Selector numbers follow Intel's discontinued R200 SDK (librealsense v1).
XU_UNIT = 2
XU_EMITTER = 8
XU_DISPARITY_SHIFT = 19
DISPARITY_SHIFT_MAX = 512

# uvcvideo's raw extension-unit access (UVCIOC_CTRL_QUERY in linux/uvcvideo.h).
_UVCIOC_CTRL_QUERY = 0xC0107521
_UVC_SET_CUR = 0x01
_UVC_GET_CUR = 0x81


class _XuQuery(ctypes.Structure):
    _fields_ = [("unit", ctypes.c_uint8), ("selector", ctypes.c_uint8), ("query", ctypes.c_uint8),
                ("size", ctypes.c_uint16), ("data", ctypes.POINTER(ctypes.c_uint8))]


def _xu_query(device: str, selector: int, query: int, data: bytes) -> bytes:
    buffer = (ctypes.c_uint8 * len(data)).from_buffer_copy(data)
    fd = os.open(device, os.O_RDWR)
    try:
        fcntl.ioctl(fd, _UVCIOC_CTRL_QUERY, _XuQuery(XU_UNIT, selector, query, len(data), buffer))
    finally:
        os.close(fd)
    return bytes(buffer)


def get_disparity_shift(control_device: str) -> int:
    return int.from_bytes(_xu_query(control_device, XU_DISPARITY_SHIFT, _UVC_GET_CUR, bytes(4)), "little")


def set_disparity_shift(control_device: str, shift: int) -> None:
    """Moves the stereo search window nearer: a higher shift measures closer objects but
    loses far ones (0 is about 0.6 m to beyond 4 m). Resets to 0 when unplugged."""
    shift = max(0, min(DISPARITY_SHIFT_MAX, shift))
    _xu_query(control_device, XU_DISPARITY_SHIFT, _UVC_SET_CUR, shift.to_bytes(4, "little"))


def set_emitter(control_device: str, on: bool) -> None:
    """The infrared dot projector gives stereo matching texture on plain surfaces (walls).
    Intel's SDK switched it on for depth; raw V4L2 streaming leaves it as it was."""
    _xu_query(control_device, XU_EMITTER, _UVC_SET_CUR, bytes([1 if on else 0]))


def find_devices() -> dict[str, str]:
    """Maps "infrared", "depth" and "colour" to their /dev/videoN paths."""
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
    """The R200's colour (BGR) and depth (uint16 millimetres, 0 = no reading) streams,
    with the infrared projector switched on."""

    def __init__(self, colour_size: tuple[int, int] = COLOUR_SIZE,
                 depth_size: tuple[int, int] = DEPTH_SIZE, fps: int = FPS) -> None:
        devices = find_devices()
        self.depth_size = depth_size
        self._control_device = devices["infrared"]
        set_emitter(self._control_device, True)
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

    @property
    def disparity_shift(self) -> int:
        return get_disparity_shift(self._control_device)

    @disparity_shift.setter
    def disparity_shift(self, shift: int) -> None:
        set_disparity_shift(self._control_device, shift)

    def close(self) -> None:
        self._colour.release()
        self._depth.release()

    def __enter__(self) -> "R200":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
