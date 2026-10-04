#!/usr/bin/env python3
"""Count people crossing a line using the IMX500 YOLO11n detector."""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
from picamera2 import Picamera2
from picamera2.devices import IMX500
from picamera2.devices.imx500 import NetworkIntrinsics

MODEL = "/usr/share/imx500-models/imx500_network_yolo11n_pp.rpk"
CONFIDENCE_THRESHOLD = 0.50
COUNTING_LINE = ((640, 100), (640, 620))
MAX_MISSED_FRAMES = 15
MIN_IOU = 0.10
MAX_CENTROID_DISTANCE = 0.08
MAX_TRACKS = 30
STATUS_INTERVAL = 1.0
PERSON_CLASS = 0

# A detection is x1, y1, x2, y2, confidence.
Detection = tuple[float, float, float, float, float]
Point = tuple[float, float]


@dataclass
class Track:
    id: int
    box: tuple[float, float, float, float]
    confidence: float
    missed: int = 0
    side: float | None = None
    counted: bool = False

    @property
    def center(self) -> Point:
        x1, y1, x2, y2 = self.box
        return (x1 + x2) / 2, (y1 + y2) / 2

    def update(self, detection: Detection) -> None:
        self.box = detection[:4]
        self.confidence = detection[4]
        self.missed = 0


def intersection_over_union(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    ax1, ay1, ax2, ay2 = first
    bx1, by1, bx2, by2 = second
    width = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    height = max(0.0, min(ay2, by2) - max(ay1, by1))
    intersection = width * height
    if not intersection:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    return intersection / (area_a + area_b - intersection)


def line_side(point: Point, start: Point, end: Point) -> float:
    x, y = point
    x1, y1 = start
    x2, y2 = end
    return (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)


class PeopleCounter:
    """Greedily track detections and count each track's first line crossing."""

    def __init__(
        self,
        frame_size: tuple[int, int],
        line: tuple[Point, Point] = COUNTING_LINE,
    ) -> None:
        width, height = frame_size
        self.frame_diagonal = (width**2 + height**2) ** 0.5
        self.line = line
        self.tracks: list[Track] = []
        self.next_id = 1
        self.in_count = 0
        self.out_count = 0

    def update(self, detections: list[Detection]) -> list[Track]:
        detections = sorted(detections, key=lambda d: d[4], reverse=True)[:MAX_TRACKS]
        candidates = []
        for track_index, track in enumerate(self.tracks):
            for detection_index, detection in enumerate(detections):
                box = detection[:4]
                overlap = intersection_over_union(track.box, box)
                x, y = track.center
                dx = (box[0] + box[2]) / 2 - x
                dy = (box[1] + box[3]) / 2 - y
                distance = (
                    (dx**2 + dy**2) ** 0.5 / self.frame_diagonal
                    if self.frame_diagonal > 0
                    else 1.0
                )
                if overlap >= MIN_IOU or distance <= MAX_CENTROID_DISTANCE:
                    candidates.append(
                        ((1 - overlap) + distance, track_index, detection_index)
                    )

        matched_tracks: set[int] = set()
        matched_detections: set[int] = set()
        for _, track_index, detection_index in sorted(candidates):
            if track_index in matched_tracks or detection_index in matched_detections:
                continue
            self.tracks[track_index].update(detections[detection_index])
            matched_tracks.add(track_index)
            matched_detections.add(detection_index)

        for index, track in enumerate(self.tracks):
            if index not in matched_tracks:
                track.missed += 1

        self.tracks = [
            track for track in self.tracks if track.missed <= MAX_MISSED_FRAMES
        ]
        for index, detection in enumerate(detections):
            if index not in matched_detections and len(self.tracks) < MAX_TRACKS:
                self.tracks.append(
                    Track(self.next_id, detection[:4], detection[4])
                )
                self.next_id += 1

        self._count_crossings()
        return self.tracks

    def _count_crossings(self) -> None:
        for track in self.tracks:
            side = line_side(track.center, *self.line)
            if track.side is not None and side * track.side < 0 and not track.counted:
                direction = "IN" if track.side < 0 else "OUT"
                if direction == "IN":
                    self.in_count += 1
                else:
                    self.out_count += 1
                track.counted = True
                print(
                    f"PERSON {track.id}: {direction} | "
                    f"IN={self.in_count} OUT={self.out_count}"
                )
            track.side = side

    def status(self) -> dict[str, int]:
        return {
            "in": self.in_count,
            "out": self.out_count,
            "total": self.in_count + self.out_count,
        }


def create_camera() -> tuple[IMX500, Picamera2, NetworkIntrinsics]:
    imx500 = IMX500(MODEL)
    intrinsics = imx500.network_intrinsics
    if intrinsics is None:
        intrinsics = NetworkIntrinsics()
        intrinsics.task = "object detection"
    elif intrinsics.task != "object detection":
        raise RuntimeError(f"Expected object-detection model, got {intrinsics.task!r}")
    intrinsics.update_with_defaults()

    camera = Picamera2(imx500.camera_num)
    camera.configure(
        camera.create_preview_configuration(
            controls={"FrameRate": intrinsics.inference_rate},
            buffer_count=12,
        )
    )
    return imx500, camera, intrinsics


def find_people(imx500: IMX500, camera: Picamera2, metadata: dict) -> list[Detection]:
    outputs = imx500.get_outputs(metadata, add_batch=True)
    if outputs is None:
        return []

    boxes, scores, classes = (np.asarray(output[0]) for output in outputs[:3])
    input_height = imx500.get_input_size()[1]
    detections = []
    for box, score, category in zip(boxes, scores, classes):
        if float(score) < CONFIDENCE_THRESHOLD or int(category) != PERSON_CLASS:
            continue
        coords = np.asarray(box, dtype=np.float32) / input_height
        coords = imx500.convert_inference_coords(
            coords[[1, 0, 3, 2]], metadata, camera
        )
        x, y, width, height = map(float, coords)
        detections.append((x, y, x + width, y + height, float(score)))
    return detections


def main() -> None:
    imx500, camera, _ = create_camera()
    print(f"Loading IMX500 model: {MODEL}")
    imx500.show_network_fw_progress_bar()
    camera.start()

    width, height = camera.camera_configuration()["main"]["size"]
    counter = PeopleCounter((width, height))
    started = last_report = time.monotonic()
    frames = 0
    print(f"Camera: {width}x{height} | Counting line: {COUNTING_LINE}")
    print("Counting people. Press Ctrl+C to stop.")

    try:
        while True:
            metadata = camera.capture_metadata()
            tracks = counter.update(find_people(imx500, camera, metadata))
            frames += 1
            now = time.monotonic()
            if now - last_report >= STATUS_INTERVAL:
                elapsed = now - started
                status = counter.status()
                print(
                    f"FPS={frames / elapsed:5.1f} | tracks={len(tracks):2d} | "
                    f"IN={status['in']:4d} | OUT={status['out']:4d} | "
                    f"TOTAL={status['total']:4d}"
                )
                last_report = now
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        camera.stop()
        print(f"Final count: {counter.status()}")


if __name__ == "__main__":
    main()
