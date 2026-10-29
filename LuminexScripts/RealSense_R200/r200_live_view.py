"""Live R200 view: colour, colour-coded depth, and depth overlaid on colour using the
camera's factory calibration (object outlines should line up in the third panel). Shows
the frame rate, the distance under the centre crosshair (check it against a tape
measure) and the nearest/furthest depth in view.

Keys: + / - change the disparity shift by 4 (] / [ by 1), q quits.

Run on the Pi's desktop, inside Luminex's .venv:
    python LuminexScripts/RealSense_R200/r200_live_view.py [--shift N]
"""

import argparse
import time

import cv2
import numpy as np

from r200_alignment import DepthToColour, load_calibration
from r200_camera import DISPARITY_SHIFT_MAX, R200

# Depth colour scale; readings outside it (and 0 = no reading) are shown black.
DEPTH_RANGE_MM = (200, 3000)
# Half-size of the centre patch whose median depth is shown, so one noisy pixel does not.
CENTRE_PATCH = 3
WINDOW = "R200 live: colour | depth | depth on colour  (q to quit)"
# How strongly the depth colours cover the colour image in the overlay panel.
OVERLAY_ALPHA = 0.5
# The R200 occasionally drops a frame (USB "-71" errors, about 1% of depth frames);
# skip those and only give up after this many in a row (about a second).
MAX_CONSECUTIVE_DROPS = 30
SHIFT_KEYS = {ord("+"): 4, ord("="): 4, ord("-"): -4, ord("]"): 1, ord("["): -1}


def colourise(depth: np.ndarray) -> np.ndarray:
    near, far = DEPTH_RANGE_MM
    valid = (depth >= near) & (depth <= far)
    scaled = np.zeros(depth.shape, dtype=np.uint8)
    scaled[valid] = ((depth[valid] - near) * 255 // (far - near)).astype(np.uint8)
    image = cv2.applyColorMap(scaled, cv2.COLORMAP_TURBO)
    image[~valid] = 0
    return image


def centre_distance_mm(depth: np.ndarray) -> int | None:
    h, w = depth.shape
    patch = depth[h // 2 - CENTRE_PATCH:h // 2 + CENTRE_PATCH + 1,
                  w // 2 - CENTRE_PATCH:w // 2 + CENTRE_PATCH + 1]
    near, far = DEPTH_RANGE_MM
    valid = patch[(patch >= near) & (patch <= far)]
    return int(np.median(valid)) if valid.size else None


def overlay(colour: np.ndarray, aligned_depth: np.ndarray) -> np.ndarray:
    """Blends colour-coded depth over the colour image where depth has a reading."""
    depth_image = colourise(aligned_depth)
    has_depth = depth_image.any(axis=2)
    blended = colour.copy()
    blended[has_depth] = cv2.addWeighted(colour, 1 - OVERLAY_ALPHA, depth_image, OVERLAY_ALPHA, 0)[has_depth]
    return blended


def depth_extent_mm(depth: np.ndarray) -> tuple[int, int] | None:
    """Nearest and furthest readings in view (1st/99th percentile, ignoring stray pixels)."""
    valid = depth[(depth > 0) & (depth < 65535)]
    if valid.size == 0:
        return None
    near, far = np.percentile(valid, [1, 99])
    return int(near), int(far)


def draw_crosshair(image: np.ndarray) -> None:
    h, w = image.shape[:2]
    cv2.drawMarker(image, (w // 2, h // 2), (255, 255, 255), cv2.MARKER_CROSS, 24, 2)


def draw_text(image: np.ndarray, text: str, line: int = 0) -> None:
    origin = (12, 32 + line * 34)
    cv2.putText(image, text, origin, cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(image, text, origin, cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--shift", type=int, help=f"disparity shift to start at (0-{DISPARITY_SHIFT_MAX})")
    args = parser.parse_args()

    calibration = load_calibration()
    aligner: DepthToColour | None = None

    with R200() as camera:
        if args.shift is not None:
            camera.disparity_shift = args.shift
        shift = camera.disparity_shift
        cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
        fps, frames, started = 0.0, 0, time.monotonic()
        drops = 0
        while True:
            colour, depth = camera.read_colour(), camera.read_depth()
            if colour is None or depth is None:
                drops += 1
                if drops >= MAX_CONSECUTIVE_DROPS:
                    print("Lost the camera stream")
                    break
                continue
            drops = 0

            if aligner is None:
                aligner = DepthToColour(calibration, depth.shape)
            depth_image = colourise(depth)
            draw_crosshair(depth_image)
            # Scale depth to the colour image's height so the panels sit side by side.
            height = colour.shape[0]
            width = round(depth_image.shape[1] * height / depth_image.shape[0])
            view = np.hstack([colour, cv2.resize(depth_image, (width, height), interpolation=cv2.INTER_NEAREST),
                              overlay(colour, aligner.align(depth))])

            frames += 1
            elapsed = time.monotonic() - started
            if elapsed >= 1.0:
                fps, frames, started = frames / elapsed, 0, time.monotonic()
            distance = centre_distance_mm(depth)
            extent = depth_extent_mm(depth)
            draw_text(view, f"{fps:4.1f} fps   centre: {f'{distance} mm' if distance else 'no reading'}")
            draw_text(view, f"disparity shift {shift}   in view: "
                            f"{f'{extent[0]}-{extent[1]} mm' if extent else 'no readings'}", line=1)

            cv2.imshow(WINDOW, view)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key in SHIFT_KEYS:
                camera.disparity_shift = shift + SHIFT_KEYS[key]
                shift = camera.disparity_shift
                print("Disparity shift:", shift)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
