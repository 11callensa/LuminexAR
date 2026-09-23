import cv2
import numpy as np
import socket
import json
import os


# =========================================================
# CONFIG — fill these in before running
# =========================================================

# Set STYLUS_TRACKER_DEBUG=1 in the environment to show the live
# OpenCV debug window (marker outlines, axes, position/orientation text).
# Leave unset (or 0) for normal app operation — no window will appear.
SHOW_DEBUG_WINDOW = os.environ.get("STYLUS_TRACKER_DEBUG", "0") == "1"
SHOW_DEBUG_WINDOW = False

CAMERA_INDEX = "/dev/video8"

FRAME_WIDTH = 640
FRAME_HEIGHT = 480


# --- Smoothing ---
# Raw per-frame ArUco pose estimates are naturally noisy (small marker,
# webcam resolution) — this applies exponential smoothing so the output
# doesn't wobble even when the stylus is held perfectly still.
# Lower = smoother but more lag. Higher = more responsive but more jitter.
POSITION_SMOOTHING_ALPHA = 0.25
ORIENTATION_SMOOTHING_ALPHA = 0.25


# --- Camera calibration ---
# These MUST come from calibrating your actual USB camera
# (e.g. OpenCV's checkerboard calibration routine).
# Values below are placeholders and will give WRONG positions
# until replaced.

CAMERA_MATRIX = np.array([
    [286.2156140069149,   0.0, 324.5622360463774],
    [  0.0, 287.05805559161655, 254.53957821315856],
    [  0.0,   0.0,              1.0]
], dtype=np.float32)

DIST_COEFFS = np.array([
    -0.07836596068835232,
     0.15429477011882933,
    -0.001598179423988055,
    -0.0004396419764734527,
    -0.08441437186131859
], dtype=np.float32)


# --- Marker physical size ---
# Side length of the black square border, in METERS.
# Measure your printed marker directly (not the whole page/border).

MARKER_LENGTH = 0.015  # e.g. 15mm marker


# --- Marker ID -> offset from marker center to stylus reference point ---
# Offset is a 3D vector, in METERS, expressed in the MARKER's own local
# frame (x right, y up, z out of the marker face).
# You need to measure/derive these from your physical mount geometry —
# e.g. from your CAD model, the vector from each marker's face center
# to the stylus tip.
#
# Fill in all 7 IDs you're using. Placeholder example below assumes
# every marker sits 0.08m from the tip along its own local -z axis;
# REPLACE with your real measurements.

MARKER_OFFSETS = {
    0: np.array([0.0495, 0.012, 0.007], dtype=np.float32),
    1: np.array([0.1144, 0, 0.007], dtype=np.float32),
    2: np.array([0.0218, 0.0015, 0.0065], dtype=np.float32),
    6: np.array([0.0, 0.0208, 0.0099], dtype=np.float32),
}


# --- UDP output ---

UDP_IP = "127.0.0.1"
UDP_PORT = 5006


# =========================================================
# ArUco setup (handles both old and new OpenCV APIs)
# =========================================================

ARUCO_DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)

try:
    # OpenCV >= 4.7 API
    ARUCO_PARAMS = cv2.aruco.DetectorParameters()
    DETECTOR = cv2.aruco.ArucoDetector(ARUCO_DICT, ARUCO_PARAMS)

    def detect_markers(gray_frame):
        corners, ids, _ = DETECTOR.detectMarkers(gray_frame)
        return corners, ids

except AttributeError:
    # Older OpenCV API fallback
    ARUCO_PARAMS = cv2.aruco.DetectorParameters_create()

    def detect_markers(gray_frame):
        corners, ids, _ = cv2.aruco.detectMarkers(
            gray_frame,
            ARUCO_DICT,
            parameters=ARUCO_PARAMS
        )
        return corners, ids


# Marker corner geometry in its own local frame, matching the corner
# ordering OpenCV returns: top-left, top-right, bottom-right, bottom-left
HALF_LEN = MARKER_LENGTH / 2.0

OBJECT_POINTS = np.array([
    [-HALF_LEN,  HALF_LEN, 0.0],
    [ HALF_LEN,  HALF_LEN, 0.0],
    [ HALF_LEN, -HALF_LEN, 0.0],
    [-HALF_LEN, -HALF_LEN, 0.0]
], dtype=np.float32)


# --- Fixed orientation correction ---
# The marker's own local axes (from OBJECT_POINTS: x-right, y-up, z-out-of-face)
# don't necessarily match how the marker sits relative to the stylus body.
# This is a CONSTANT correction, applied identically to every marker,
# not something that varies frame to frame. Tune by trial and error:
# try combinations of 0/90/-90/180 on each axis until the virtual
# stylus's orientation matches the real one when held in various poses.
ORIENTATION_CORRECTION_EULER_DEG = (0, 0, 180)  # (x, y, z) — start here, then adjust


def euler_deg_to_rotation_matrix(rx_deg, ry_deg, rz_deg):
    rx = np.radians(rx_deg)
    ry = np.radians(ry_deg)
    rz = np.radians(rz_deg)

    Rx = np.array([
        [1, 0, 0],
        [0, np.cos(rx), -np.sin(rx)],
        [0, np.sin(rx), np.cos(rx)]
    ])

    Ry = np.array([
        [np.cos(ry), 0, np.sin(ry)],
        [0, 1, 0],
        [-np.sin(ry), 0, np.cos(ry)]
    ])

    Rz = np.array([
        [np.cos(rz), -np.sin(rz), 0],
        [np.sin(rz), np.cos(rz), 0],
        [0, 0, 1]
    ])

    return Rz @ Ry @ Rx


ORIENTATION_CORRECTION_MATRIX = euler_deg_to_rotation_matrix(*ORIENTATION_CORRECTION_EULER_DEG)


def rotation_matrix_to_quaternion(R):
    """
    Convert a 3x3 rotation matrix to a quaternion (w, x, y, z).
    Standard, numerically stable conversion.
    """

    trace = R[0, 0] + R[1, 1] + R[2, 2]

    if trace > 0:
        s = 0.5 / np.sqrt(trace + 1.0)
        w = 0.25 / s
        x = (R[2, 1] - R[1, 2]) * s
        y = (R[0, 2] - R[2, 0]) * s
        z = (R[1, 0] - R[0, 1]) * s

    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = 2.0 * np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2])
        w = (R[2, 1] - R[1, 2]) / s
        x = 0.25 * s
        y = (R[0, 1] + R[1, 0]) / s
        z = (R[0, 2] + R[2, 0]) / s

    elif R[1, 1] > R[2, 2]:
        s = 2.0 * np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2])
        w = (R[0, 2] - R[2, 0]) / s
        x = (R[0, 1] + R[1, 0]) / s
        y = 0.25 * s
        z = (R[1, 2] + R[2, 1]) / s

    else:
        s = 2.0 * np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1])
        w = (R[1, 0] - R[0, 1]) / s
        x = (R[0, 2] + R[2, 0]) / s
        y = (R[1, 2] + R[2, 1]) / s
        z = 0.25 * s

    return np.array([w, x, y, z], dtype=np.float32)


def quaternion_slerp(q_from, q_to, t):
    """
    Spherical linear interpolation between two quaternions (w, x, y, z).
    Used for smoothing orientation — quaternions can't be smoothed with
    simple averaging the way positions can.
    """

    q_from = q_from / np.linalg.norm(q_from)
    q_to = q_to / np.linalg.norm(q_to)

    dot = np.dot(q_from, q_to)

    # take the shorter path around the sphere
    if dot < 0.0:
        q_to = -q_to
        dot = -dot

    dot = np.clip(dot, -1.0, 1.0)

    # nearly identical — linear interpolation is a safe, stable fallback
    if dot > 0.9995:
        result = q_from + t * (q_to - q_from)
        return result / np.linalg.norm(result)

    theta_0 = np.arccos(dot)
    theta = theta_0 * t

    q_perp = q_to - q_from * dot
    q_perp = q_perp / np.linalg.norm(q_perp)

    return q_from * np.cos(theta) + q_perp * np.sin(theta)


# =========================================================
# Main loop
# =========================================================

cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

smoothed_position = None
smoothed_orientation = None


try:
    while True:

        ret, frame = cap.read()

        if not ret:
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        corners, ids = detect_markers(gray)

        estimated_points = []

        best_orientation_quat = None
        best_headon_score = -1.0  # higher = more directly facing the camera

        if ids is not None:

            if SHOW_DEBUG_WINDOW:
                cv2.aruco.drawDetectedMarkers(frame, corners, ids)

            for marker_corners, marker_id in zip(corners, ids.flatten()):

                marker_id = int(marker_id)

                if marker_id not in MARKER_OFFSETS:
                    continue

                image_points = marker_corners.reshape(4, 2).astype(np.float32)

                success, rvec, tvec = cv2.solvePnP(
                    OBJECT_POINTS,
                    image_points,
                    CAMERA_MATRIX,
                    DIST_COEFFS
                )

                if not success:
                    continue

                rotation_matrix, _ = cv2.Rodrigues(rvec)

                offset = MARKER_OFFSETS[marker_id]

                # transform the local offset into the camera's frame
                # using this marker's own orientation, then add its
                # translation to get the reference point in camera space
                reference_point = (
                    rotation_matrix @ offset
                    +
                    tvec.flatten()
                )

                estimated_points.append(reference_point)

                # how directly this marker faces the camera:
                # marker's own local Z axis (its face normal), rotated
                # into camera space, compared against the direction
                # pointing back at the camera. 1.0 = dead-on, 0.0 = edge-on
                marker_normal = rotation_matrix @ np.array([0.0, 0.0, 1.0])
                to_camera = -tvec.flatten()
                to_camera = to_camera / (np.linalg.norm(to_camera) + 1e-6)

                headon_score = np.dot(marker_normal, to_camera)

                if headon_score > best_headon_score:
                    best_headon_score = headon_score
                    corrected_rotation = rotation_matrix @ ORIENTATION_CORRECTION_MATRIX
                    best_orientation_quat = rotation_matrix_to_quaternion(corrected_rotation)

                if SHOW_DEBUG_WINDOW:
                    # draw this marker's own axes for visual debugging
                    cv2.drawFrameAxes(
                        frame,
                        CAMERA_MATRIX,
                        DIST_COEFFS,
                        rvec,
                        tvec,
                        MARKER_LENGTH * 0.75
                    )

        stylus_position = None

        if len(estimated_points) > 0:

            # average across all currently visible markers for stability
            raw_position = np.mean(
                np.array(estimated_points),
                axis=0
            )

            if smoothed_position is None:
                # just reacquired after being invisible — snap directly,
                # don't smooth from a stale/nonexistent previous value
                smoothed_position = raw_position
            else:
                smoothed_position = (
                    smoothed_position * (1.0 - POSITION_SMOOTHING_ALPHA)
                    +
                    raw_position * POSITION_SMOOTHING_ALPHA
                )

            stylus_position = smoothed_position

            if best_orientation_quat is not None:
                if smoothed_orientation is None:
                    smoothed_orientation = best_orientation_quat
                else:
                    smoothed_orientation = quaternion_slerp(
                        smoothed_orientation,
                        best_orientation_quat,
                        ORIENTATION_SMOOTHING_ALPHA
                    )

            if SHOW_DEBUG_WINDOW:
                cv2.putText(
                    frame,
                    f"Stylus pos (m): "
                    f"({stylus_position[0]:.3f}, "
                    f"{stylus_position[1]:.3f}, "
                    f"{stylus_position[2]:.3f})",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 0),
                    2
                )

                cv2.putText(
                    frame,
                    f"Markers visible: {len(estimated_points)}",
                    (10, 55),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 0),
                    2
                )

        else:

            # stylus not visible — clear smoothing state so the next
            # reacquisition snaps cleanly rather than smoothing from
            # a now-irrelevant old position/orientation
            smoothed_position = None
            smoothed_orientation = None

            if SHOW_DEBUG_WINDOW:
                cv2.putText(
                    frame,
                    "No markers visible",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 0, 255),
                    2
                )


        # always send a packet, every frame, so Godot can tell the
        # difference between "no data yet" and "stylus genuinely not visible"

        if stylus_position is not None:

            message = json.dumps({
                "type": "STYLUS_POS",
                "visible": True,
                "position": stylus_position.tolist(),
                "orientation": smoothed_orientation.tolist()
                    if smoothed_orientation is not None else None,
                "markers_visible": len(estimated_points)
            })

        else:

            message = json.dumps({
                "type": "STYLUS_POS",
                "visible": False,
                "position": None,
                "orientation": None,
                "markers_visible": 0
            })

        sock.sendto(
            message.encode("utf-8"),
            (UDP_IP, UDP_PORT)
        )


        if SHOW_DEBUG_WINDOW:
            cv2.imshow("Stylus Tracker", frame)

            if cv2.waitKey(1) == ord("q"):
                break

finally:

    cap.release()
    sock.close()

    if SHOW_DEBUG_WINDOW:
        cv2.destroyAllWindows()
