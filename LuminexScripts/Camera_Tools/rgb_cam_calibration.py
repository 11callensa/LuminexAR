import cv2
import numpy as np
import json


# =========================================================
# CONFIG — fill these in to match your printed checkerboard
# =========================================================

CAMERA_INDEX = 0

FRAME_WIDTH = 640
FRAME_HEIGHT = 480

# Number of INTERNAL corners, not squares.
# e.g. a 10x7 grid of squares has 9x6 internal corners.
# OpenCV's own pattern.png is 9x6.
CHECKERBOARD = (8, 5)

# Real, measured side length of one square, in METERS.
# Measure this on your actual printout — don't trust the
# nominal value if there's any chance it didn't print at 100% scale.
SQUARE_SIZE = 0.0186  # e.g. 25mm

# How many good checkerboard detections to collect before calibrating.
# 15-20 is a reasonable range — more helps up to a point.
NUM_SAMPLES_NEEDED = 20

OUTPUT_FILE = "camera_calibration.json"


# =========================================================
# Setup
# =========================================================

# 3D coordinates of checkerboard corners in the board's own frame,
# z=0 since the board is flat. e.g. (0,0,0), (1,0,0), (2,0,0)... * SQUARE_SIZE
objp = np.zeros((CHECKERBOARD[0] * CHECKERBOARD[1], 3), np.float32)
objp[:, :2] = np.mgrid[
    0:CHECKERBOARD[0],
    0:CHECKERBOARD[1]
].T.reshape(-1, 2)
objp *= SQUARE_SIZE

object_points = []   # 3D points, one array per accepted sample
image_points = []    # corresponding 2D points, one array per accepted sample

criteria = (
    cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
    30,
    0.001
)


cap = cv2.VideoCapture("/dev/video8", cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)


print("Move the checkerboard around in view of the camera.")
print("Press SPACE to capture a sample when the board is detected (highlighted).")
print(f"Need {NUM_SAMPLES_NEEDED} samples. Press 'q' to quit early.")


try:
    while len(object_points) < NUM_SAMPLES_NEEDED:

        ret, frame = cap.read()

        if not ret:
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        found, corners = cv2.findChessboardCorners(
            gray,
            CHECKERBOARD,
            None
        )

        display = frame.copy()

        if found:

            corners_refined = cv2.cornerSubPix(
                gray,
                corners,
                (11, 11),
                (-1, -1),
                criteria
            )

            cv2.drawChessboardCorners(
                display,
                CHECKERBOARD,
                corners_refined,
                found
            )

        cv2.putText(
            display,
            f"Samples: {len(object_points)}/{NUM_SAMPLES_NEEDED}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0) if found else (0, 0, 255),
            2
        )

        cv2.putText(
            display,
            "SPACE = capture   Q = quit",
            (10, 55),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1
        )

        cv2.imshow("Calibration", display)

        key = cv2.waitKey(1)

        if key == ord("q"):
            break

        if key == ord(" ") and found:

            object_points.append(objp)
            image_points.append(corners_refined)

            print(f"Captured sample {len(object_points)}/{NUM_SAMPLES_NEEDED}")

finally:

    cap.release()
    cv2.destroyAllWindows()


# =========================================================
# Run calibration
# =========================================================

if len(object_points) < 5:

    print("Not enough samples captured — need at least 5 to calibrate.")
    print(f"Only got {len(object_points)}. Run again and capture more.")

else:

    print(f"Calibrating using {len(object_points)} samples...")

    ret, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(
        object_points,
        image_points,
        (FRAME_WIDTH, FRAME_HEIGHT),
        None,
        None
    )

    print("\nCalibration complete.")
    print("Reprojection error:", ret)
    print("(Lower is better — under ~0.5 is generally good, over ~1.0 suggests")
    print("retaking samples with more angle variety or a flatter board.)\n")

    print("CAMERA_MATRIX =")
    print(camera_matrix)

    print("\nDIST_COEFFS =")
    print(dist_coeffs)


    # save to file for easy loading in stylus_tracker.py

    output = {
        "camera_matrix": camera_matrix.tolist(),
        "dist_coeffs": dist_coeffs.tolist(),
        "reprojection_error": ret
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nSaved to {OUTPUT_FILE}")