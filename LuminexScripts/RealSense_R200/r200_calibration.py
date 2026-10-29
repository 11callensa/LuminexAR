"""Reads the R200's factory calibration from its flash memory and prints it as JSON.

Every R200 was calibrated individually at the factory; the result (lens intrinsics for
the depth and colour cameras and the transform between them) lives in the camera's
flash. Intel's discontinued R200 SDK (librealsense v1.12, src/ds-private.cpp) read it
through the extension unit's command channel; this repeats those reads. Read-only: it
only issues flash *read* commands.

Run on the Pi with the camera plugged in (and not streaming):
    python LuminexScripts/RealSense_R200/r200_calibration.py > r200_calibration.json
"""

import json
import math
import struct

from r200_camera import _UVC_GET_CUR, _UVC_SET_CUR, _xu_query, find_devices

XU_COMMAND_RESPONSE = 1
COMMAND_DOWNLOAD_SPI_FLASH = 0x1A
COMMAND_MODIFIER_DIRECT = 0x10
COMMAND_TAG = 12
PAGE_BYTES = 0x100
SECTOR_BYTES = 0x1000
# The admin table (addresses of the data sectors) starts after the 160 firmware sectors.
ADMIN_TABLE_ADDRESS = 160 * SECTOR_BYTES
CALIBRATION_ADMIN_INDEX = 0
HEAD_CONTENT_OFFSET = 2048
# The depth stream crops 6 pixels from each edge of the rectified 640x481 left image.
DEPTH_CROP = 6


def _read_flash(device: str, address: int, pages: int) -> bytes:
    """Reads whole 256-byte pages: one command, then one response read per page."""
    command = struct.pack("<5I", COMMAND_DOWNLOAD_SPI_FLASH, COMMAND_MODIFIER_DIRECT, COMMAND_TAG,
                          address, pages * PAGE_BYTES) + bytes(59 * 4)
    _xu_query(device, XU_COMMAND_RESPONSE, _UVC_SET_CUR, command)
    _xu_query(device, XU_COMMAND_RESPONSE, _UVC_GET_CUR, bytes(len(command)))
    return b"".join(_xu_query(device, XU_COMMAND_RESPONSE, _UVC_GET_CUR, bytes(PAGE_BYTES))
                    for _ in range(pages))


def read_calibration_sector(device: str) -> bytes:
    admin_table = struct.unpack("<9I", _read_flash(device, ADMIN_TABLE_ADDRESS, 1)[:36])
    return _read_flash(device, admin_table[CALIBRATION_ADMIN_INDEX], SECTOR_BYTES // PAGE_BYTES)


class _BigEndian:
    """Sequential reader for the calibration table, which is stored big-endian."""

    def __init__(self, data: bytes) -> None:
        self.data, self.offset = data, 0

    def read(self, fmt: str) -> tuple:
        values = struct.unpack_from(">" + fmt, self.data, self.offset)
        self.offset += struct.calcsize(">" + fmt)
        return values


def _unrectified(reader: _BigEndian, distortion_fmt: str) -> dict:
    fx, fy, ppx, ppy = reader.read("4f")
    coeffs = list(reader.read(distortion_fmt))
    width, height = reader.read("2I")
    return {"width": width, "height": height, "fx": fx, "fy": fy, "ppx": ppx, "ppy": ppy,
            "model": "modified_brown_conrady", "coeffs": coeffs}


def _rectified(reader: _BigEndian) -> dict:
    fx, fy, ppx, ppy = reader.read("4f")
    width, height = reader.read("2I")
    return {"width": width, "height": height, "fx": fx, "fy": fy, "ppx": ppx, "ppy": ppy,
            "model": "none", "coeffs": [0.0] * 5}


def parse_calibration(sector: bytes) -> dict:
    """Decodes the table layouts of librealsense v1 (versions 0, 1 and 2)."""
    reader = _BigEndian(sector)
    (version,) = reader.read("I")
    if version == 0:
        reader.read("4H")
        distortion, intrinsics_counts, modes_lr, modes_third, matrix = "5d", (1, 2, 3), (2, 4), (2, 3, 4), "9d"
    elif version in (1, 2):
        reader.read("6H")
        distortion, intrinsics_counts, modes_lr, modes_third, matrix = "5f", (1, 2, 3, 4), (2, 4), (2, 3, 3), "9f"
    else:
        raise ValueError(f"Unsupported calibration version {version}")

    groups = [[_unrectified(reader, distortion) for _ in range(n)] for n in intrinsics_counts]
    intrinsics_third = groups[2]
    rectified_lr = [[_rectified(reader) for _ in range(modes_lr[1])] for _ in range(modes_lr[0])]
    for _ in range(math.prod(modes_third)):
        _rectified(reader)
    if version != 0:
        for _ in range(2 * 4):  # platform camera modes, unused on the R200
            _rectified(reader)
    reader.read(matrix * 2)  # Rleft
    reader.read(matrix * 2)  # Rright
    r_third = list(reader.read(matrix * 2)[:9])
    if version != 0:
        reader.read(matrix * 2)  # Rplatform
    baseline_mm = reader.read("2f")[0]
    t_mm = list(reader.read("6f")[:3])

    serial, = struct.unpack_from("<I", sector, HEAD_CONTENT_OFFSET)
    nominal_baseline_third_mm, = struct.unpack_from("<i", sector, HEAD_CONTENT_OFFSET + 100)

    lr = rectified_lr[0][0]
    depth = dict(lr, width=lr["width"] - 2 * DEPTH_CROP, height=lr["height"] - 2 * DEPTH_CROP,
                 ppx=lr["ppx"] - DEPTH_CROP, ppy=lr["ppy"] - DEPTH_CROP)
    # A depth-frame point maps to colour as Rthird * p + Rthird * T. (Reading librealsense
    # v1's pose code suggested the inverse; on the real camera that put the overlay 59 mm
    # the wrong way, and the overlay lines up with this direction.)
    r_depth_to_colour = r_third
    t_depth_to_colour_mm = [sum(r_third[i * 3 + j] * t_mm[j] for j in range(3)) for i in range(3)]
    return {
        "camera": "Intel RealSense R200",
        "serial": serial,
        "calibration_table_version": version,
        "stereo_baseline_mm": baseline_mm,
        "nominal_baseline_colour_mm": nominal_baseline_third_mm,
        "depth_628x469": depth,
        "colour_1920x1080": intrinsics_third[0],
        "colour_640x480": intrinsics_third[1],
        "depth_to_colour": {
            "rotation_row_major": r_depth_to_colour,
            "translation_m": [t / 1000.0 for t in t_depth_to_colour_mm],
        },
        "raw": {"Rthird_row_major": r_third, "T_mm": t_mm, "rectified_lr_modes": rectified_lr[0][:3]},
    }


def main() -> None:
    sector = read_calibration_sector(find_devices()["infrared"])
    print(json.dumps(parse_calibration(sector), indent=2))


if __name__ == "__main__":
    main()
