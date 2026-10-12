#!/usr/bin/env python3
"""Count people crossing a line using IMX500 detections and Supervision."""

from __future__ import annotations

from pathlib import Path
import time
from typing import Any

import cv2
import numpy as np
import supervision as sv
from picamera2 import Picamera2
from picamera2.devices import IMX500
from picamera2.devices.imx500 import NetworkIntrinsics
from trackers import ByteTrackTracker

from yaki import config

conf = config.load("camera").get("imx500", {})

MODEL = conf.get("MODEL", "/usr/share/imx500-models/imx500_network_yolo11n_pp.rpk")
COUNTING_LINE = conf.get("COUNTING_LINE", ((640, 100), (640, 620)))
PERSON_CLASS = 0

WIDTH = conf.get("WIDTH", 1280)
HEIGHT = conf.get("HEIGHT", 720)

LINE_ZONE = sv.LineZone(
    start=sv.Point(x=int(COUNTING_LINE[0][0]), y=int(COUNTING_LINE[0][1])),
    end=sv.Point(x=int(COUNTING_LINE[1][0]), y=int(COUNTING_LINE[1][1])),
)

box_annotator = sv.BoxAnnotator()
label_annotator = sv.LabelAnnotator()
line_annotator = sv.LineZoneAnnotator()

missing_jpg = Path(__file__).parent.parent / "missing.jpg"

return_frame = False

intrinsics_fps = 12

count_enabled = True

def create_camera(
    capture_images: bool = False,
) -> tuple[IMX500, Picamera2]:
    imx500 = IMX500(MODEL)
    intrinsics = imx500.network_intrinsics
    if intrinsics is None:
        intrinsics = NetworkIntrinsics()
        intrinsics.task = "object detection"
    elif intrinsics.task != "object detection":
        raise RuntimeError(f"Expected object-detection model, got {intrinsics.task!r}")
    intrinsics.update_with_defaults()

    intrinsics_fps = intrinsics.inference_rate
    camera = Picamera2(imx500.camera_num)
    preview_options = {
        "main": { "size": (WIDTH, HEIGHT), "format": "RGB888" },
        "controls": {"FrameRate": intrinsics_fps},
        "buffer_count": 12,
    }
    camera.configure(camera.create_preview_configuration(**preview_options))
    return imx500, camera


def find_people(
    imx500: IMX500,
    camera: Picamera2,
    metadata: dict[str, Any],
    detect_floor=0.2
) -> sv.Detections | None:
    """Convert this frame's IMX500 output to Supervision detections."""
    outputs = imx500.get_outputs(metadata, add_batch=True)
    if outputs is None or len(outputs) < 3:
        return None

    boxes, scores, classes = (np.asarray(output[0]) for output in outputs[:3])
    input_height = imx500.get_input_size()[1]
    person_boxes = []
    person_scores = []

    for box, score, category in zip(boxes, scores, classes):
        score = float(score)
        if (
            score <= detect_floor
            or int(category) != PERSON_CLASS
        ):
            continue

        # YOLO11n post-processed boxes are normalized and in y/x order.
        coords = np.asarray(box, dtype=np.float32) / input_height
        x, y, width, height = imx500.convert_inference_coords(
            coords[[1, 0, 3, 2]], metadata, camera
        )
        x1, y1, x2, y2 = map(float, (x, y, x + width, y + height))
        if (
            all(np.isfinite(value) for value in (x1, y1, x2, y2))
            and x2 > x1
            and y2 > y1
        ):
            person_boxes.append((x1, y1, x2, y2))
            person_scores.append(score)

    return sv.Detections(
        xyxy=np.asarray(person_boxes, dtype=np.float32).reshape(-1, 4),
        confidence=np.asarray(person_scores, dtype=np.float32),
        class_id=np.full(len(person_scores), PERSON_CLASS, dtype=int),
    )

def annotate_frame(
    frame: np.ndarray,
    detections: sv.Detections,
    tracked: sv.Detections,
    line_zone: sv.LineZone
) -> np.ndarray:
    scene = frame.copy()
    tracker_ids = tracked.tracker_id
    confidences = tracked.confidence
    if confidences is None:
        confidences = np.zeros(len(tracked), dtype=np.float32)
    if tracker_ids is None:
        labels = [f"person {confidence:.2f}" for confidence in confidences]
    else:
        labels = [
            f"person #{int(track_id)} {confidence:.2f}"
            for track_id, confidence in zip(tracker_ids, confidences)
        ]
    scene = box_annotator.annotate(scene=scene, detections=detections)
    scene = box_annotator.annotate(scene=scene, detections=tracked)
    scene = label_annotator.annotate(
        scene=scene, detections=tracked, labels=labels
    )
    return line_annotator.annotate(frame=scene, line_counter=line_zone)



def main_count_loop(callback, invert_ins_outs=False, detect_floor=0.2, track_timeout = 2, track_threshold = 0.5, confidence_threshold = 0.5, min_consecutive_frames = 2) -> None:

    imx500, camera = create_camera()

    imx500.show_network_fw_progress_bar()

    while not camera.started:
        try:
            camera.start()
        except Exception as e:
            print(e)
            time.sleep(2)

    tracker = ByteTrackTracker(
        lost_track_buffer=round(track_timeout * 30),
        frame_rate=intrinsics_fps,
        track_activation_threshold=confidence_threshold,
        minimum_consecutive_frames=min_consecutive_frames,
        high_conf_det_threshold=track_threshold,
    )

    while camera.is_open and count_enabled:
        request = camera.capture_request()
        try:
            metadata = request.get_metadata()
            detections = find_people(imx500, camera, metadata, detect_floor)
            frame = request.make_array("main")
        finally:
            request.release()

        if detections is not None:
            tracked = tracker.update(detections)
            LINE_ZONE.trigger(tracked)

            if return_frame:
                frame = annotate_frame(
                    frame,
                    detections,
                    tracked,
                    LINE_ZONE
                )
                _, frame = cv2.imencode('.jpg', frame)
                frame = frame.tobytes()
            else:
                frame = None

            if invert_ins_outs:
                callback(LINE_ZONE.out_count, LINE_ZONE.in_count, frame)
            else:
                callback(LINE_ZONE.in_count, LINE_ZONE.out_count, frame)

    camera.close()
