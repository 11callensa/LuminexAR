"""
FastSAM on Hailo - fixed pipeline, FPS-optimized.

Display modified to match the Hailo edge-detection model:
- Darkened background
- Zoom/crop
- Screen-aspect-ratio crop
- True fullscreen window
- Segmentation masks drawn over the darkened image

The FastSAM inference pipeline itself is unchanged.
"""

import subprocess
import numpy as np
import cv2
import torch
from ultralytics.utils.nms import non_max_suppression
from ultralytics.utils.ops import process_mask
from hailo_platform import (
    HEF,
    VDevice,
    InputVStreamParams,
    OutputVStreamParams,
    InferVStreams,
    FormatType,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

HEF_PATH = "fast_sam_s.hef"
INFER_SHAPE = (640, 640)

REG_MAX = 16
NUM_CLASSES = 1
NUM_MASKS = 32
CONF_THRES = 0.6
IOU_THRES = 0.4
MAX_DET = 100

# ---------------------------------------------------------------------------
# Display settings
# ---------------------------------------------------------------------------

ZOOM_FACTOR = 2.9
VERTICAL_OFFSET = 0.0

BACKGROUND_SCALE = 0.1
BACKGROUND_BRIGHTNESS = 10

WINDOW_NAME = "FastSAM"

# ---------------------------------------------------------------------------
# Get screen resolution
# ---------------------------------------------------------------------------

def get_screen_resolution():
    output = subprocess.check_output(
        "xrandr | grep '*'",
        shell=True
    ).decode()

    resolution = output.split()[0]
    width, height = map(int, resolution.split('x'))

    return width, height


SCREEN_WIDTH, SCREEN_HEIGHT = get_screen_resolution()

print("Screen:", SCREEN_WIDTH, SCREEN_HEIGHT)

# ---------------------------------------------------------------------------
# Fullscreen window
# ---------------------------------------------------------------------------

cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
cv2.setWindowProperty(
    WINDOW_NAME,
    cv2.WND_PROP_FULLSCREEN,
    cv2.WINDOW_FULLSCREEN
)
cv2.moveWindow(WINDOW_NAME, 0, 0)

# ---------------------------------------------------------------------------
# Load HEF
# ---------------------------------------------------------------------------

hef = HEF(HEF_PATH)


# ---------------------------------------------------------------------------
# Precomputed anchors
# ---------------------------------------------------------------------------

def _build_anchors():
    anchors, strides = [], []

    for stride in SCALE_OUTPUTS:
        h, w = INFER_SHAPE[0] // stride, INFER_SHAPE[1] // stride

        gy, gx = torch.meshgrid(
            torch.arange(h, dtype=torch.float32),
            torch.arange(w, dtype=torch.float32),
            indexing="ij",
        )

        a = torch.stack(
            (gx, gy),
            dim=-1
        ).reshape(-1, 2) + 0.5

        anchors.append(a * stride)
        strides.append(
            torch.full(
                (h * w,),
                float(stride)
            )
        )

    return (
        torch.cat(anchors),
        torch.cat(strides).unsqueeze(1)
    )


SCALE_OUTPUTS = {
    8: {
        "box": "fast_sam_s/conv45",
        "obj": "fast_sam_s/conv46",
        "mask": "fast_sam_s/conv44"
    },

    16: {
        "box": "fast_sam_s/conv61",
        "obj": "fast_sam_s/conv62",
        "mask": "fast_sam_s/conv60"
    },

    32: {
        "box": "fast_sam_s/conv74",
        "obj": "fast_sam_s/conv75",
        "mask": "fast_sam_s/conv73"
    },
}

PROTO_NAME = "fast_sam_s/conv48"

_ANCHORS, _STRIDES = _build_anchors()
_BINS = torch.arange(REG_MAX, dtype=torch.float32)


# ---------------------------------------------------------------------------
# Decode outputs
# ---------------------------------------------------------------------------

def decode_outputs(output_dict):

    box_all = []
    obj_all = []
    mask_all = []

    for stride, names in SCALE_OUTPUTS.items():

        box_all.append(
            torch.from_numpy(
                output_dict[names["box"]][0]
            ).reshape(-1, 4 * REG_MAX)
        )

        obj_all.append(
            torch.from_numpy(
                output_dict[names["obj"]][0]
            ).reshape(-1, NUM_CLASSES)
        )

        mask_all.append(
            torch.from_numpy(
                output_dict[names["mask"]][0]
            ).reshape(-1, NUM_MASKS)
        )

    box = torch.cat(box_all)
    obj = torch.cat(obj_all)
    mask = torch.cat(mask_all)

    n = box.shape[0]

    ltrb = (
        box.view(n, 4, REG_MAX)
        .softmax(dim=2)
        * _BINS
    ).sum(dim=2) * _STRIDES

    x1 = _ANCHORS[:, 0] - ltrb[:, 0]
    y1 = _ANCHORS[:, 1] - ltrb[:, 1]
    x2 = _ANCHORS[:, 0] + ltrb[:, 2]
    y2 = _ANCHORS[:, 1] + ltrb[:, 3]

    xywh = torch.stack(
        (
            (x1 + x2) / 2,
            (y1 + y2) / 2,
            x2 - x1,
            y2 - y1
        ),
        dim=1
    )

    conf = obj.sigmoid()

    pred = torch.cat(
        (xywh, conf, mask),
        dim=1
    ).T.unsqueeze(0)

    proto = torch.from_numpy(
        output_dict[PROTO_NAME][0]
    ).permute(2, 0, 1)

    return pred, proto


# ---------------------------------------------------------------------------
# Undo inference stretching
# ---------------------------------------------------------------------------

def unstretch_boxes(boxes, infer_shape, orig_shape):

    ih, iw = infer_shape
    oh, ow = orig_shape

    boxes[:, [0, 2]] *= ow / iw
    boxes[:, [1, 3]] *= oh / ih

    boxes[:, [0, 2]] = boxes[:, [0, 2]].clamp(0, ow)
    boxes[:, [1, 3]] = boxes[:, [1, 3]].clamp(0, oh)

    return boxes


# ---------------------------------------------------------------------------
# Postprocess
# ---------------------------------------------------------------------------

def postprocess(pred, proto, orig_shape):

    p = non_max_suppression(
        pred,
        conf_thres=CONF_THRES,
        iou_thres=IOU_THRES,
        agnostic=False,
        max_det=MAX_DET,
        nc=NUM_CLASSES,
        classes=None,
    )

    det = p[0]

    if det is None or len(det) == 0:
        return None

    det[:, :4] = unstretch_boxes(
        det[:, :4].clone(),
        INFER_SHAPE,
        orig_shape
    )

    masks = process_mask(
        proto,
        det[:, 6:],
        det[:, :4],
        orig_shape,
        upsample=True
    )

    return det, masks


# ---------------------------------------------------------------------------
# Tracking
# ---------------------------------------------------------------------------

IOU_MATCH_THRES = 0.3
MAX_MISSED = 30


def _iou(box1, box2):

    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])

    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])

    inter = (
        max(0.0, x2 - x1)
        *
        max(0.0, y2 - y1)
    )

    area1 = (
        (box1[2] - box1[0])
        *
        (box1[3] - box1[1])
    )

    area2 = (
        (box2[2] - box2[0])
        *
        (box2[3] - box2[1])
    )

    union = area1 + area2 - inter

    return inter / union if union > 0 else 0.0


class Track:

    __slots__ = ("box", "color", "missed")

    def __init__(self, box, color):
        self.box = box
        self.color = color
        self.missed = 0


class SimpleTracker:

    def __init__(
        self,
        iou_thres=IOU_MATCH_THRES,
        max_missed=MAX_MISSED
    ):

        self.tracks = []
        self.iou_thres = iou_thres
        self.max_missed = max_missed

    def update(self, boxes):

        n = len(boxes)

        assigned = [None] * n

        pairs = []

        for ti, t in enumerate(self.tracks):

            for di, b in enumerate(boxes):

                v = _iou(t.box, b)

                if v >= self.iou_thres:
                    pairs.append((v, di, ti))

        pairs.sort(
            key=lambda p: p[0],
            reverse=True
        )

        used_dets = set()
        used_tracks = set()

        for _, di, ti in pairs:

            if di in used_dets or ti in used_tracks:
                continue

            used_dets.add(di)
            used_tracks.add(ti)

            t = self.tracks[ti]

            t.box = boxes[di]
            t.missed = 0

            assigned[di] = t

        for di in range(n):

            if assigned[di] is None:

                color = tuple(
                    int(c)
                    for c in np.random.randint(
                        0,
                        256,
                        3
                    )
                )

                t = Track(
                    boxes[di],
                    color
                )

                self.tracks.append(t)

                assigned[di] = t

        for ti, t in enumerate(self.tracks):

            if ti not in used_tracks:
                t.missed += 1

        self.tracks = [
            t
            for t in self.tracks
            if t.missed <= self.max_missed
        ]

        return [
            t.color
            for t in assigned
        ]


_tracker = SimpleTracker()


# ---------------------------------------------------------------------------
# ZOOM
# ---------------------------------------------------------------------------

def zoom_frame(frame):

    h, w = frame.shape[:2]

    new_w = int(w / ZOOM_FACTOR)
    new_h = int(h / ZOOM_FACTOR)

    start_x = (w - new_w) // 2

    max_offset = h - new_h

    start_y = int(
        (max_offset / 2)
        +
        (VERTICAL_OFFSET * max_offset / 2)
    )

    start_y = max(
        0,
        min(start_y, max_offset)
    )

    zoomed = frame[
        start_y:start_y + new_h,
        start_x:start_x + new_w
    ]

    return cv2.resize(
        zoomed,
        (w, h)
    )


# ---------------------------------------------------------------------------
# Create screen-fitted display
# ---------------------------------------------------------------------------

def fit_to_screen(image):

    h, w = image.shape[:2]

    target_ratio = SCREEN_WIDTH / SCREEN_HEIGHT
    current_ratio = w / h

    if current_ratio > target_ratio:

        new_w = int(h * target_ratio)

        start_x = (w - new_w) // 2

        cropped = image[
            :,
            start_x:start_x + new_w
        ]

    else:

        new_h = int(w / target_ratio)

        start_y = (h - new_h) // 2

        cropped = image[
            start_y:start_y + new_h,
            :
        ]

    return cv2.resize(
        cropped,
        (SCREEN_WIDTH, SCREEN_HEIGHT)
    )


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------
def draw_detections(frame, det, masks):

    # -------------------------------------------------------
    # Completely black background
    # -------------------------------------------------------

    # overlay = np.zeros_like(frame)
    overlay = frame.copy()

    if masks is None:
        return overlay

    colors = _tracker.update(
        det[:, :4].tolist()
    )

    for i in range(det.shape[0]):

        mask = masks[i].numpy().astype(bool)

        color = np.array(
            colors[i],
            dtype=np.float32
        )

        # ---------------------------------------------------
        # Fill segment
        # ---------------------------------------------------

        overlay[mask] = (
            0.5 * overlay[mask]
            + 0.5 * color
        ).astype(np.uint8)

        # ---------------------------------------------------
        # Black boundary
        # ---------------------------------------------------

        mask_uint8 = (
            mask.astype(np.uint8) * 255
        )

        contours, _ = cv2.findContours(
            mask_uint8,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        cv2.drawContours(
            overlay,
            contours,
            -1,
            (0, 0, 0),
            2
        )

    return overlay


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

with VDevice() as device:

    network_group = device.configure(hef)[0]

    network_params = network_group.create_params()

    input_vparams = InputVStreamParams.make(
        network_group
    )

    output_vparams = OutputVStreamParams.make(
        network_group,
        quantized=False,
        format_type=FormatType.FLOAT32
    )

    with network_group.activate(network_params):

        with InferVStreams(
            network_group,
            input_vparams,
            output_vparams
        ) as infer_pipeline:

            input_name = (
                hef
                .get_input_vstream_infos()[0]
                .name
            )

            cap = cv2.VideoCapture(8)

            with torch.inference_mode():

                while True:

                    ret, frame = cap.read()

                    if not ret:
                        break

                    # ---------------------------------------------------
                    # ORIGINAL FASTSAM INFERENCE
                    # ---------------------------------------------------

                    rgb = cv2.cvtColor(
                        frame,
                        cv2.COLOR_BGR2RGB
                    )

                    input_data = cv2.resize(
                        rgb,
                        (
                            INFER_SHAPE[1],
                            INFER_SHAPE[0]
                        )
                    )

                    input_data = np.expand_dims(
                        input_data.astype(np.uint8),
                        axis=0
                    )

                    output_dict = infer_pipeline.infer(
                        {input_name: input_data}
                    )

                    pred, proto = decode_outputs(
                        output_dict
                    )

                    result = postprocess(
                        pred,
                        proto,
                        frame.shape[:2]
                    )

                    # ---------------------------------------------------
                    # ZOOM FOR DISPLAY
                    # ---------------------------------------------------

                    frame_display = zoom_frame(frame)

                    # ---------------------------------------------------
                    # IMPORTANT:
                    # The masks were generated against the original
                    # frame dimensions.
                    #
                    # Therefore zoom the completed segmentation image,
                    # rather than zooming the input before inference.
                    # ---------------------------------------------------

                    if result is not None:

                        det, masks = result

                        # Start with the original RGB camera image
                        segmented = frame.copy()

                        # Draw the segmentation on top
                        segmented = draw_detections(
                                segmented,
                                det,
                                masks
                            )

                    else:

                        # No detections → just show the RGB image
                        segmented = frame.copy()




                    # if result is not None:

                    #     det, masks = result

                    #     segmented = draw_detections(
                    #         frame,
                    #         det,
                    #         masks
                    #     )

                    # else:

                    #     segmented = (
                    #         frame
                    #         * BACKGROUND_SCALE
                    #         +
                    #         BACKGROUND_BRIGHTNESS
                    #     ).astype(np.uint8)




                    # Apply same zoom to final result
                    segmented = zoom_frame(
                        segmented
                    )

                    # ---------------------------------------------------
                    # Fit to physical screen aspect ratio
                    # ---------------------------------------------------

                    display = fit_to_screen(
                        segmented
                    )

                    # ---------------------------------------------------
                    # Fullscreen display
                    # ---------------------------------------------------

                    cv2.imshow(
                        WINDOW_NAME,
                        display
                    )

                    if cv2.waitKey(1) & 0xFF == 27:
                        break

            cap.release()
            cv2.destroyAllWindows()