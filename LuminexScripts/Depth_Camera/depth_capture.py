"""
depth_capture.py

Reads stable depth frames from the Arducam ToF camera.
"""

import cv2
import numpy as np
import ArducamDepthCamera as ac


class DepthCamera:

    def __init__(self):

        self.camera = ac.ArducamCamera()

        self.max_distance = 4000

        self.previous_depth = None

        self.alpha = 0.35       # temporal smoothing

    def open(self):

        ret = self.camera.open(ac.Connection.CSI, 0)

        if ret != ac.TofErrorCode.ArducamSuccess:
            raise RuntimeError(f"Failed to open camera: {ret}")

        ret = self.camera.start(ac.FrameType.DEPTH)

        if ret != ac.TofErrorCode.ArducamSuccess:
            raise RuntimeError(f"Failed to start depth stream: {ret}")

        self.camera.setControl(
            ac.Control.RANGE,
            self.max_distance
        )

    def close(self):

        self.camera.stop()
        self.camera.close()

    def get_depth(self):

        frame = self.camera.requestFrame(200)

        if frame is None:
            return None

        depth = frame.depth_data.copy()

        self.camera.releaseFrame(frame)

        # remove NaNs

        depth = np.nan_to_num(depth)

        # remove invalid pixels

        depth[depth < 50] = 0
        depth[depth > self.max_distance] = 0

        # Median filter removes ToF speckle

        depth = cv2.medianBlur(
            depth.astype(np.float32),
            5
        )

        # Gaussian smooths remaining noise

        depth = cv2.GaussianBlur(
            depth,
            (5,5),
            0
        )

        # Temporal smoothing

        if self.previous_depth is None:

            self.previous_depth = depth.copy()

        else:

            self.previous_depth = (
                self.alpha * depth +
                (1-self.alpha) * self.previous_depth
            )

        return self.previous_depth.copy()