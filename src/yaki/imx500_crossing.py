#!/usr/bin/env python3
"""Count people crossing a line using IMX500 detections and Supervision."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

import numpy as np
import supervision as sv
from trackers import ByteTrackTracker
from PIL import Image
from picamera2 import Picamera2
from picamera2.devices import IMX500
from yaki.better_imx500_counter import (
    create_camera,
    create_preview_window,
    display_frame,
)

MODEL = "/usr/share/imx500-models/imx500_network_yolo11n_pp.rpk"
CONFIDENCE_THRESHOLD = 0.80
TRACKING_FLOOR = 0.10
COUNTING_LINE = ((640, 100), (640, 620))
TRACK_TIMEOUT = 2.0
STATUS_INTERVAL = 1.0
PERSON_CLASS = 0


def find_people(
    imx500: IMX500,
    camera: Picamera2,
    metadata: dict[str, Any],
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
            not np.isfinite(score)
            or score < TRACKING_FLOOR
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


def make_line_zone() -> sv.LineZone:
    start, end = COUNTING_LINE
    return sv.LineZone(
        start=sv.Point(x=int(start[0]), y=int(start[1])),
        end=sv.Point(x=int(end[0]), y=int(end[1])),
    )


def annotate_frame(
    frame: np.ndarray,
    detections: sv.Detections,
    line_zone: sv.LineZone,
    box_annotator: sv.BoxAnnotator,
    label_annotator: sv.LabelAnnotator,
    line_annotator: sv.LineZoneAnnotator,
) -> Image.Image:
    """Draw tracked boxes and the crossing line onto a captured RGB frame."""
    # Supervision/OpenCV annotators use BGR; Picamera2 provides RGB888.
    scene = frame[:, :, ::-1].copy()
    tracker_ids = detections.tracker_id
    confidences = detections.confidence
    if confidences is None:
        confidences = np.zeros(len(detections), dtype=np.float32)
    if tracker_ids is None:
        labels = [f"person {confidence:.2f}" for confidence in confidences]
    else:
        labels = [
            f"person #{int(track_id)} {confidence:.2f}"
            for track_id, confidence in zip(tracker_ids, confidences)
        ]
    scene = box_annotator.annotate(scene=scene, detections=detections)
    scene = label_annotator.annotate(
        scene=scene, detections=detections, labels=labels
    )
    scene = line_annotator.annotate(frame=scene, line_counter=line_zone)
    return Image.fromarray(scene[:, :, ::-1])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--save-frame",
        metavar="PATH",
        type=Path,
        help="save one annotated JPEG after the first inference result",
    )
    parser.add_argument(
        "--display",
        action="store_true",
        help="show an annotated live preview in a Tkinter window",
    )
    args = parser.parse_args()
    capture_images = args.display or args.save_frame is not None

    imx500, camera, intrinsics = create_camera(capture_images=capture_images)
    print(f"Loading IMX500 model: {MODEL}")
    imx500.show_network_fw_progress_bar()
    preview = create_preview_window() if args.display else None
    camera_started = False
    line_zone = make_line_zone()

    try:
        camera.start()
        camera_started = True
        width, height = camera.camera_configuration()["main"]["size"]
        frame_rate = max(1, round(intrinsics.inference_rate))
        tracker = ByteTrackTracker(
            lost_track_buffer=round(TRACK_TIMEOUT * 30),
            frame_rate=frame_rate,
            track_activation_threshold=CONFIDENCE_THRESHOLD,
            minimum_consecutive_frames=2,
            high_conf_det_threshold=CONFIDENCE_THRESHOLD,
        )
        box_annotator = sv.BoxAnnotator()
        label_annotator = sv.LabelAnnotator()
        line_annotator = sv.LineZoneAnnotator()
        started = last_report = time.monotonic()
        frames = 0

        print(f"Camera: {width}x{height} | Counting line: {COUNTING_LINE}")
        print("Counting people. Press Ctrl+C to stop.")

        while True:
            request = camera.capture_request()
            try:
                metadata = request.get_metadata()
                detections = find_people(imx500, camera, metadata)
                has_inference = detections is not None
                need_frame = args.display or args.save_frame is not None
                frame = request.make_array("main") if need_frame else None
            finally:
                request.release()

            if detections is None:
                # Advance ByteTrack on every camera frame but preserve the
                # distinction between unavailable inference and zero detections.
                detections = sv.Detections(
                    xyxy=np.empty((0, 4), dtype=np.float32),
                    confidence=np.empty(0, dtype=np.float32),
                    class_id=np.empty(0, dtype=int),
                )

            tracked = tracker.update(detections)
            line_zone.trigger(tracked)

            if frame is not None:
                annotated = annotate_frame(
                    frame,
                    tracked,
                    line_zone,
                    box_annotator,
                    label_annotator,
                    line_annotator,
                )
                if args.save_frame is not None and has_inference:
                    annotated.save(args.save_frame, format="JPEG", quality=90)
                    print(f"Saved annotated frame to {args.save_frame}")
                    args.save_frame = None
                if preview is not None:
                    window, label, state = preview
                    if not display_frame(window, label, annotated, state):
                        break

            frames += 1
            now = time.monotonic()
            if now - last_report >= STATUS_INTERVAL:
                elapsed = now - started
                print(
                    f"FPS={frames / elapsed:5.1f} | tracks={len(tracked):2d} | "
                    f"IN={line_zone.in_count:4d} | OUT={line_zone.out_count:4d} | "
                    f"TOTAL={line_zone.in_count + line_zone.out_count:4d}"
                )
                last_report = now
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        if camera_started:
            camera.stop()
        if preview is not None:
            window, _, _ = preview
            window.destroy()
        print(
            f"Final count: IN={line_zone.in_count}, OUT={line_zone.out_count}, "
            f"TOTAL={line_zone.in_count + line_zone.out_count}"
        )


if __name__ == "__main__":
    main()
