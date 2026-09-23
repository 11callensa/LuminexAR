import subprocess
import numpy as np
import cv2
from hailo_platform import HEF, VDevice, InputVStreamParams, OutputVStreamParams, InferVStreams

# ---- User settings ----
CONFIDENCE_THRESHOLD = 170  # 0-255
LINE_THICKNESS = 1          # Edge thickness

ZOOM_FACTOR = 2.9
VERTICAL_OFFSET = 0.28

# ---- Load HEF ----
hef = HEF("unet_model_hailo.hef")

# ---- Get screen resolution ----
def get_screen_resolution():
    output = subprocess.check_output("xrandr | grep '*'", shell=True).decode()
    resolution = output.split()[0]
    width, height = map(int, resolution.split('x'))
    return width, height

SCREEN_WIDTH, SCREEN_HEIGHT = get_screen_resolution()
print("Screen:", SCREEN_WIDTH, SCREEN_HEIGHT)

# ---- Create TRUE fullscreen window ----
WINDOW_NAME = "Hailo UNet Edges"
cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
cv2.moveWindow(WINDOW_NAME, 0, 0)

with VDevice() as device:
    network_group = device.configure(hef)[0]
    network_params = network_group.create_params()

    # ---- VStream params ----
    input_vparams = InputVStreamParams.make(network_group)
    output_vparams = OutputVStreamParams.make(network_group)

    # ---- Activate network group ----
    with network_group.activate(network_params):
        with InferVStreams(network_group, input_vparams, output_vparams) as infer_pipeline:
            input_name = hef.get_input_vstream_infos()[0].name

            # ---- Open camera ----
            cap = cv2.VideoCapture(0)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                # ---- Zoom (center crop) ----
                h, w = frame.shape[:2]

                new_w = int(w / ZOOM_FACTOR)
                new_h = int(h / ZOOM_FACTOR)

                # Horizontal stays centered
                start_x = (w - new_w) // 2

                # Vertical shift
                max_offset = h - new_h
                start_y = int((max_offset / 2) + (VERTICAL_OFFSET * max_offset / 2))

                # Clamp to valid range
                start_y = max(0, min(start_y, max_offset))

                zoomed = frame[start_y:start_y + new_h, start_x:start_x + new_w]

                # Resize back to original size (so rest of pipeline stays unchanged)
                frame_zoomed = cv2.resize(zoomed, (w, h))

                # ---- Preprocess ----
                resized = cv2.resize(frame_zoomed, (128, 128))
                input_data = np.expand_dims(resized.astype(np.uint8), axis=0)

                # ---- Inference ----
                input_dict = {input_name: input_data}
                output_dict = infer_pipeline.infer(input_dict)

                # ---- Postprocess ----
                output_data = list(output_dict.values())[0]
                mask = np.squeeze(output_data)

                # ---- Threshold ----
                _, mask_thresh = cv2.threshold(mask, CONFIDENCE_THRESHOLD, 255, cv2.THRESH_BINARY)

                # ---- Edge detection ----
                edges = cv2.Canny(mask_thresh, 50, 150)

                # ---- Thicken edges ----
                kernel = np.ones((LINE_THICKNESS, LINE_THICKNESS), np.uint8)
                edges_thick = cv2.dilate(edges, kernel, iterations=1)

                # ---- Resize edges to match frame ----
                edges_resized = cv2.resize(
                    edges_thick,
                    (frame.shape[1], frame.shape[0]),
                    interpolation=cv2.INTER_NEAREST
                )

                # ---- Overlay edges ----
#                 overlay = frame_zoomed.copy()
#                 overlay[edges_resized > 0] = [0, 255, 180]

                # Create black image
#                 overlay = np.zeros_like(frame_zoomed)
#                 overlay = np.full_like(frame_zoomed, 50)

                overlay = (frame_zoomed * 0.1 + 10).astype(np.uint8)

                # Draw edges only
                overlay[edges_resized > 0] = [0, 255, 180]

                # ---- Crop to screen aspect ratio (no stretching) ----
                h, w = overlay.shape[:2]
                target_ratio = SCREEN_WIDTH / SCREEN_HEIGHT
                current_ratio = w / h

                if current_ratio > target_ratio:
                    new_w = int(h * target_ratio)
                    start_x = (w - new_w) // 2
                    cropped = overlay[:, start_x:start_x + new_w]
                else:
                    new_h = int(w / target_ratio)
                    start_y = (h - new_h) // 2
                    cropped = overlay[start_y:start_y + new_h, :]

                # ---- Resize to fullscreen ----
                overlay_full = cv2.resize(cropped, (SCREEN_WIDTH, SCREEN_HEIGHT))

                cv2.imshow(WINDOW_NAME, overlay_full)

                if cv2.waitKey(1) & 0xFF == 27:
                    break

            cap.release()
            cv2.destroyAllWindows()