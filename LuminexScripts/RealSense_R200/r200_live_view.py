"""Live R200 view: colour beside colour-coded depth, with the frame rate and the distance
under the centre crosshair (check it against a tape measure). Press q to quit.

Run on the Pi's desktop, inside Luminex's .venv:
    python LuminexScripts/RealSense_R200/r200_live_view.py
"""

import time

import cv2
import numpy as np

from r200_camera import R200

# Depth colour scale; readings outside it (and 0 = no reading) are shown black.
DEPTH_RANGE_MM = (300, 5000)
# Half-size of the centre patch whose median depth is shown, so one noisy pixel does not.
CENTRE_PATCH = 3
WINDOW = "R200 live: colour | depth  (q to quit)"


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


def draw_crosshair(image: np.ndarray) -> None:
    h, w = image.shape[:2]
    cv2.drawMarker(image, (w // 2, h // 2), (255, 255, 255), cv2.MARKER_CROSS, 24, 2)


def draw_text(image: np.ndarray, text: str) -> None:
    cv2.putText(image, text, (12, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(image, text, (12, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)


def main() -> None:
    with R200() as camera:
        cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
        fps, frames, started = 0.0, 0, time.monotonic()
        while True:
            colour, depth = camera.read_colour(), camera.read_depth()
            if colour is None or depth is None:
                print("Lost the camera stream")
                break

            depth_image = colourise(depth)
            draw_crosshair(depth_image)
            # Scale depth to the colour image's height so the two sit side by side.
            height = colour.shape[0]
            width = round(depth_image.shape[1] * height / depth_image.shape[0])
            view = np.hstack([colour, cv2.resize(depth_image, (width, height), interpolation=cv2.INTER_NEAREST)])

            frames += 1
            elapsed = time.monotonic() - started
            if elapsed >= 1.0:
                fps, frames, started = frames / elapsed, 0, time.monotonic()
            distance = centre_distance_mm(depth)
            draw_text(view, f"{fps:4.1f} fps   centre: {f'{distance} mm' if distance else 'no reading'}")

            cv2.imshow(WINDOW, view)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
