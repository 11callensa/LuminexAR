import cv2
import numpy as np
import os

from depth_capture import DepthCamera
from depth_segmentation import segment_depth
from normal_estimator import fit_plane

import socket
import json


# Set SURFACE_VISUALISER_DEBUG=1 in the environment to show the live
# OpenCV debug window (depth view, plane overlays, contours, text).
# Leave unset (or 0) for normal app operation — no window will appear.
SHOW_DEBUG_WINDOW = os.environ.get("SURFACE_VISUALISER_DEBUG", "0") == "1"

SHOW_DEBUG_WINDOW = True

# Physical offset between the ToF depth camera and the RGB camera used
# for stylus tracking, so both data streams share one consistent frame.
# Measured: ToF sits 14.5mm ABOVE the RGB camera on the glasses temple,
# same horizontal position, no depth offset between them.
CAMERA_OFFSET_TOF_TO_RGB = np.array([0.0, -0.0145, 0.0], dtype=np.float32)


camera = DepthCamera()
camera.open()

UDP_IP = "127.0.0.1"
UDP_PORT = 5007

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


FX=190.92
FY=191.25
CX=120
CY=90


try:
    while True:

        depth = camera.get_depth()

        if depth is None:
            continue
        
        # Camera is mounted upside down
        depth = cv2.rotate(
            depth,
            cv2.ROTATE_180
        )


        mask, points = segment_depth(
            depth,
            FX,
            FY,
            CX,
            CY
        )


        # foreground surface
        surface_mask = (
            mask == 1
        ).astype(
            np.uint8
        )


        # clean holes and noise

        kernel = np.ones(
            (10,10),
            np.uint8
        )


        surface_mask = cv2.morphologyEx(
            surface_mask,
            cv2.MORPH_CLOSE,
            kernel
        )


        surface_mask = cv2.morphologyEx(
            surface_mask,
            cv2.MORPH_OPEN,
            kernel
        )



        # find connected regions

        num, labels, stats, _ = cv2.connectedComponentsWithStats(
            surface_mask,
            connectivity=8
        )


        # ignore background (label 0), rank remaining components by area

        top_labels = []

        if num > 1:

            areas = [
                (i, stats[i, cv2.CC_STAT_AREA])
                for i in range(1, num)
            ]

            areas.sort(
                key=lambda x: x[1],
                reverse=True
            )

            top_labels = [
                label for label, area in areas[:3]
            ]


        depth_view = None

        if SHOW_DEBUG_WINDOW:
            # depth image for display (built once, drawn on per-region below)

            depth_view = cv2.normalize(
                depth,
                None,
                0,
                255,
                cv2.NORM_MINMAX
            ).astype(
                np.uint8
            )

            depth_view = cv2.cvtColor(
                depth_view,
                cv2.COLOR_GRAY2BGR
            )

        planes_this_frame = []

        # process each candidate region independently

        for region_label in top_labels:

            region_mask = (
                labels == region_label
            ).astype(np.uint8)


            # planarity check on this region

            is_planar = False
            inlier_ratio = 0.0

            region_points = points[region_mask == 1]

            if region_points.shape[0] > 200:

                centroid, normal, residuals = fit_plane(
                    region_points
                )

                # ensure normal always faces the camera (origin)
                if np.dot(normal, centroid) > 0:
                    normal = -normal

                inlier_thresh = 8  # mm

                inliers = residuals < inlier_thresh

                inlier_ratio = inliers.sum() / residuals.shape[0]

                is_planar = inlier_ratio > 0.9

                region_indices = np.argwhere(region_mask == 1)
                outlier_indices = region_indices[~inliers]

                region_mask[
                    outlier_indices[:,0],
                    outlier_indices[:,1]
                ] = 0


            if not is_planar:
                continue


            if SHOW_DEBUG_WINDOW:
                # translucent overlay for this region

                overlay = depth_view.copy()

                overlay[
                    region_mask == 1
                ] = (
                    0,
                    255,
                    0
                )

                depth_view = cv2.addWeighted(
                    overlay,
                    0.35,
                    depth_view,
                    0.65,
                    0
                )


            # find boundary

            contours,_ = cv2.findContours(
                region_mask,
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_SIMPLE
            )

            if len(contours):

                contour = max(
                    contours,
                    key=cv2.contourArea
                )

                if SHOW_DEBUG_WINDOW:
                    cv2.drawContours(
                        depth_view,
                        [contour],
                        -1,
                        (0,0,255),
                        3
                    )

                epsilon = (
                    0.02 *
                    cv2.arcLength(
                        contour,
                        True
                    )
                )

                approx = cv2.approxPolyDP(
                    contour,
                    epsilon,
                    True
                )

                if SHOW_DEBUG_WINDOW:
                    cv2.polylines(
                        depth_view,
                        [approx],
                        True,
                        (255,0,0),
                        3
                    )

                # convert 2D pixel corners to 3D using the same points array
                corners_flat = []

                for pt in approx:
                    px, py = pt[0]
                    p3d = points[py, px] + CAMERA_OFFSET_TOF_TO_RGB
                    corners_flat.extend([
                        float(p3d[0]),
                        float(p3d[1]),
                        float(p3d[2])
                    ])

                planes_this_frame.append({
                    "centroid": (centroid + CAMERA_OFFSET_TOF_TO_RGB).tolist(),
                    "normal": normal.tolist(),
                    "corners_flat": corners_flat
                })

                if SHOW_DEBUG_WINDOW:
                    # label this region near its own contour

                    x, y, w, h = cv2.boundingRect(contour)

                    cv2.putText(
                        depth_view,
                        f"Corners: {len(approx)} Planar: {is_planar} ({inlier_ratio:.2f})",
                        (x, max(y - 10, 20)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (255,255,255),
                        2
                    )

                    cv2.putText(
                        depth_view,
                        f"Normal: ({normal[0]:.2f}, {normal[1]:.2f}, {normal[2]:.2f})",
                        (x, max(y - 30, 40)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (0,255,255),
                        2
                    )

                    # draw an arrow showing the normal direction

                    cx_px = x + w // 2
                    cy_px = y + h // 2

                    arrow_len = 40

                    end_x = int(cx_px + normal[0] * arrow_len)
                    end_y = int(cy_px + normal[1] * arrow_len)

                    cv2.arrowedLine(
                        depth_view,
                        (cx_px, cy_px),
                        (end_x, end_y),
                        (0,255,255),
                        2,
                        tipLength=0.3
                    )

        message = json.dumps({
            "planes": planes_this_frame
        })

        sock.sendto(
            message.encode("utf-8"),
            (UDP_IP, UDP_PORT)
        )

        if SHOW_DEBUG_WINDOW:
            cv2.imshow(
                "Detected Surface",
                depth_view
            )

            if cv2.waitKey(1)==ord("q"):
                break

finally:

    camera.close()
    sock.close()

    if SHOW_DEBUG_WINDOW:
        cv2.destroyAllWindows()