#!/usr/bin/env python3
"""Count people visible to a Raspberry Pi AI Camera (IMX500)."""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
from picamera2 import Picamera2
from picamera2.devices import IMX500
from picamera2.devices.imx500 import NetworkIntrinsics

MODEL = "/usr/share/imx500-models/imx500_network_yolo11n_pp.rpk"
PERSON_CLASS = 0
CONFIDENCE_THRESHOLD = 0.45
TRACK_TIMEOUT = 2.0
MAX_CENTER_DISTANCE = 0.08
MIN_IOU = 0.10
STATUS_INTERVAL = 1.0

Box = tuple[float, float, float, float]


@dataclass
class PersonTrack:
    box: Box
    last_seen: float


def detect_people(
    imx500: IMX500,
    camera: Picamera2,
    metadata: dict,
) -> list[Box] | None:
    """Return person boxes, or None when this request has no inference output."""
    outputs = imx500.get_outputs(metadata, add_batch=True)
    if outputs is None or len(outputs) < 3:
        return None

    boxes, scores, classes = (np.asarray(output[0]) for output in outputs[:3])
    input_height = imx500.get_input_size()[1]
    people = []

    for box, score, category in zip(boxes, scores, classes):
        if (
            not np.isfinite(score)
            or float(score) < CONFIDENCE_THRESHOLD
            or int(category) != PERSON_CLASS
        ):
            continue

        # YOLO11n's post-processed boxes use normalized model coordinates and
        # y/x ordering; convert them to the camera output coordinate system.
        coords = np.asarray(box, dtype=np.float32) / input_height
        x, y, width, height = imx500.convert_inference_coords(
            coords[[1, 0, 3, 2]], metadata, camera
        )
        values = tuple(map(float, (x, y, x + width, y + height)))
        valid_box = (
            all(np.isfinite(value) for value in values)
            and values[2] > values[0]
            and values[3] > values[1]
        )
        if valid_box:
            people.append(values)

    return people


def intersection_over_union(first: Box, second: Box) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    overlap = max(0.0, right - left) * max(0.0, bottom - top)
    if overlap == 0:
        return 0.0
    first_area = (first[2] - first[0]) * (first[3] - first[1])
    second_area = (second[2] - second[0]) * (second[3] - second[1])
    return overlap / (first_area + second_area - overlap)


class PeopleTracker:
    """Stabilize the visible-person count across intermittent missed inferences."""

    def __init__(
        self,
        frame_size: tuple[int, int],
        timeout: float = TRACK_TIMEOUT,
    ) -> None:
        width, height = frame_size
        self.frame_diagonal = (width**2 + height**2) ** 0.5
        self.timeout = timeout
        self.tracks: list[PersonTrack] = []

    def update(
        self,
        detections: list[Box] | None,
        now: float | None = None,
    ) -> int:
        now = time.monotonic() if now is None else now
        self.tracks = [
            track for track in self.tracks if now - track.last_seen <= self.timeout
        ]

        if detections is not None:
            matches = []
            for track_index, track in enumerate(self.tracks):
                for detection_index, detection in enumerate(detections):
                    overlap = intersection_over_union(track.box, detection)
                    tx = (track.box[0] + track.box[2]) / 2
                    ty = (track.box[1] + track.box[3]) / 2
                    dx = (detection[0] + detection[2]) / 2 - tx
                    dy = (detection[1] + detection[3]) / 2 - ty
                    distance = (
                        (dx**2 + dy**2) ** 0.5 / self.frame_diagonal
                        if self.frame_diagonal
                        else 1.0
                    )
                    if overlap >= MIN_IOU or distance <= MAX_CENTER_DISTANCE:
                        matches.append(
                            (1 - overlap + distance, track_index, detection_index)
                        )

            matched_tracks: set[int] = set()
            matched_detections: set[int] = set()
            for _, track_index, detection_index in sorted(matches):
                if track_index in matched_tracks or detection_index in matched_detections:
                    continue
                track = self.tracks[track_index]
                track.box = detections[detection_index]
                track.last_seen = now
                matched_tracks.add(track_index)
                matched_detections.add(detection_index)

            self.tracks.extend(
                PersonTrack(box, now)
                for index, box in enumerate(detections)
                if index not in matched_detections
            )

        return len(self.tracks)


def create_camera() -> tuple[IMX500, Picamera2]:
    imx500 = IMX500(MODEL)
    intrinsics = imx500.network_intrinsics
    if intrinsics is None:
        intrinsics = NetworkIntrinsics()
        intrinsics.task = "object detection"
    elif intrinsics.task != "object detection":
        raise RuntimeError(
            f"Expected an object-detection model, got {intrinsics.task!r}"
        )
    intrinsics.update_with_defaults()

    camera = Picamera2(imx500.camera_num)
    camera.configure(
        camera.create_preview_configuration(
            controls={"FrameRate": intrinsics.inference_rate},
            buffer_count=12,
        )
    )
    return imx500, camera


def main() -> None:
    imx500, camera = create_camera()
    print(f"Loading IMX500 model: {MODEL}")
    imx500.show_network_fw_progress_bar()
    camera.start()

    width, height = camera.camera_configuration()["main"]["size"]
    tracker = PeopleTracker((width, height))
    last_report = time.monotonic()
    count = 0
    print(f"Camera: {width}x{height}")
    print("Counting people in the camera view. Press Ctrl+C to stop.")

    try:
        while True:
            request = camera.capture_request()
            try:
                # Read inference output from the metadata belonging to this frame.
                metadata = request.get_metadata()
                detections = detect_people(imx500, camera, metadata)
            finally:
                request.release()

            count = tracker.update(detections)
            now = time.monotonic()
            if now - last_report >= STATUS_INTERVAL:
                print(f"People in frame: {count}")
                last_report = now
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        camera.stop()
        print(f"Final people-in-frame estimate: {count}")


if __name__ == "__main__":
    main()
