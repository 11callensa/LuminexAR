"""Maps R200 depth pixels onto the colour image, using the camera's factory calibration
(see r200_calibration.py). The depth and colour cameras sit 59 mm apart, so the same
pixel coordinates do not show the same point until depth is re-projected like this.
"""

import json
from pathlib import Path

import numpy as np

CALIBRATION_DIR = Path(__file__).parent


def load_calibration(path: Path | None = None) -> dict:
    """The given calibration file, or the only r200_calibration_*.json next to this script."""
    if path is None:
        found = sorted(CALIBRATION_DIR.glob("r200_calibration_*.json"))
        if len(found) != 1:
            raise RuntimeError(f"Expected one r200_calibration_*.json in {CALIBRATION_DIR}, found {len(found)}; "
                               "pass the file explicitly")
        path = found[0]
    return json.loads(Path(path).read_text())


class DepthToColour:
    """Re-projects a depth frame into the colour camera's 640x480 image."""

    def __init__(self, calibration: dict, depth_shape: tuple[int, int]) -> None:
        depth = calibration["depth_628x469"]
        self.colour = calibration["colour_640x480"]
        extrinsics = calibration["depth_to_colour"]
        self.rotation = np.array(extrinsics["rotation_row_major"], dtype=np.float32).reshape(3, 3)
        self.translation = np.array(extrinsics["translation_m"], dtype=np.float32)
        # Each depth pixel's viewing ray only depends on the depth intrinsics, so compute once.
        rows, cols = np.indices(depth_shape, dtype=np.float32)
        self.ray_x = ((cols - depth["ppx"]) / depth["fx"]).ravel()
        self.ray_y = ((rows - depth["ppy"]) / depth["fy"]).ravel()

    def align(self, depth_mm: np.ndarray) -> np.ndarray:
        """Depth in millimetres as seen from the colour camera (0 = no reading)."""
        z = depth_mm.ravel().astype(np.float32) / 1000.0
        valid = (z > 0) & (depth_mm.ravel() < 65535)
        points = np.stack([self.ray_x[valid] * z[valid], self.ray_y[valid] * z[valid], z[valid]])
        points = self.rotation @ points + self.translation[:, None]
        u, v = self._project(points)

        width, height = self.colour["width"], self.colour["height"]
        inside = (u >= 0) & (u < width) & (v >= 0) & (v < height) & (points[2] > 0)
        aligned = np.zeros((height, width), dtype=np.uint16)
        aligned[v[inside], u[inside]] = (points[2, inside] * 1000.0).astype(np.uint16)
        return aligned

    def _project(self, points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Pinhole projection with librealsense v1's modified Brown-Conrady distortion."""
        c = self.colour
        k1, k2, p1, p2, k3 = c["coeffs"]
        x, y = points[0] / points[2], points[1] / points[2]
        r2 = x * x + y * y
        radial = 1 + k1 * r2 + k2 * r2 * r2 + k3 * r2 * r2 * r2
        x, y = x * radial, y * radial
        x, y = x + 2 * p1 * x * y + p2 * (r2 + 2 * x * x), y + 2 * p2 * x * y + p1 * (r2 + 2 * y * y)
        u = np.round(x * c["fx"] + c["ppx"]).astype(np.int32)
        v = np.round(y * c["fy"] + c["ppy"]).astype(np.int32)
        return u, v
