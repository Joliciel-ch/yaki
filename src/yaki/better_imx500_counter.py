#!/usr/bin/env python3
"""Count people crossing a line using the IMX500 YOLO11n detector."""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from picamera2 import Picamera2
from picamera2.devices import IMX500
from picamera2.devices.imx500 import NetworkIntrinsics

MODEL = "/usr/share/imx500-models/imx500_network_yolo11n_pp.rpk"
CONFIDENCE_THRESHOLD = 0.80
COUNTING_LINE = ((640, 100), (640, 620))
TRACK_TIMEOUT = 2.0
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
    side: float | None = None
    counted: bool = False
    last_seen: float = 0.0

    @property
    def center(self) -> Point:
        x1, y1, x2, y2 = self.box
        return (x1 + x2) / 2, (y1 + y2) / 2

    def update(self, detection: Detection, now: float) -> None:
        self.box = detection[:4]
        self.confidence = detection[4]
        self.last_seen = now


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

    def update(
        self,
        detections: list[Detection] | None,
        now: float | None = None,
    ) -> list[Track]:
        now = time.monotonic() if now is None else now
        self.tracks = [
            track for track in self.tracks if now - track.last_seen <= TRACK_TIMEOUT
        ]

        # Missing inference output is not a negative detection. Keep existing
        # tracks until they expire, without incrementing their missed-frame count.
        if detections is None:
            self._count_crossings()
            return self.tracks

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
            self.tracks[track_index].update(detections[detection_index], now)
            matched_tracks.add(track_index)
            matched_detections.add(detection_index)

        for index, detection in enumerate(detections):
            if index not in matched_detections and len(self.tracks) < MAX_TRACKS:
                self.tracks.append(
                    Track(self.next_id, detection[:4], detection[4], last_seen=now)
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


def create_camera(
    capture_images: bool = False,
) -> tuple[IMX500, Picamera2, NetworkIntrinsics]:
    imx500 = IMX500(MODEL)
    intrinsics = imx500.network_intrinsics
    if intrinsics is None:
        intrinsics = NetworkIntrinsics()
        intrinsics.task = "object detection"
    elif intrinsics.task != "object detection":
        raise RuntimeError(f"Expected object-detection model, got {intrinsics.task!r}")
    intrinsics.update_with_defaults()

    camera = Picamera2(imx500.camera_num)
    preview_options = {
        "controls": {"FrameRate": intrinsics.inference_rate},
        "buffer_count": 12,
    }
    if capture_images:
        preview_options["main"] = {"format": "RGB888"}
    camera.configure(camera.create_preview_configuration(**preview_options))
    return imx500, camera, intrinsics


def annotate_frame(
    frame: np.ndarray,
    tracks: list[Track],
    line: tuple[Point, Point] = COUNTING_LINE,
) -> np.ndarray:
    """Draw the line and tracks onto a Picamera2 RGB888/OpenCV BGR frame."""
    image = frame.copy()
    start = (round(line[0][0]), round(line[0][1]))
    end = (round(line[1][0]), round(line[1][1]))
    cv2.line(image, start, end, (0, 255, 255), 3)
    for track in tracks:
        x1, y1, x2, y2 = track.box
        x1, y1, x2, y2 = map(round, (x1, y1, x2, y2))
        cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 3)
        cv2.putText(
            image,
            f"Person {track.id} ({track.confidence:.2f})",
            (x1, max(18, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            2,
        )
    return image


def save_annotated_frame(
    frame: np.ndarray,
    tracks: list[Track],
    path: str | Path,
    line: tuple[Point, Point] = COUNTING_LINE,
) -> None:
    """Write one annotated camera frame to a JPEG file using OpenCV."""
    if not cv2.imwrite(str(path), annotate_frame(frame, tracks, line)):
        raise OSError(f"Could not save image to {path}")


def find_people(
    imx500: IMX500,
    camera: Picamera2,
    metadata: dict,
) -> list[Detection] | None:
    outputs = imx500.get_outputs(metadata, add_batch=True)
    if outputs is None or len(outputs) < 3:
        return None

    boxes, scores, classes = (np.asarray(output[0]) for output in outputs[:3])
    input_height = imx500.get_input_size()[1]
    detections = []
    for box, score, category in zip(boxes, scores, classes):
        if (
            not np.isfinite(score)
            or float(score) < CONFIDENCE_THRESHOLD
            or int(category) != PERSON_CLASS
        ):
            continue
        coords = np.asarray(box, dtype=np.float32) / input_height
        coords = imx500.convert_inference_coords(
            coords[[1, 0, 3, 2]], metadata, camera
        )
        x, y, width, height = map(float, coords)
        box_values = (x, y, x + width, y + height)
        if (
            all(np.isfinite(value) for value in box_values)
            and width > 0
            and height > 0
        ):
            detections.append((*box_values, float(score)))
    return detections


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
        help="show an annotated live preview in an OpenCV window (press q to quit)",
    )
    args = parser.parse_args()

    capture_images = args.display or args.save_frame is not None
    imx500, camera, _ = create_camera(capture_images=capture_images)
    print(f"Loading IMX500 model: {MODEL}")
    imx500.show_network_fw_progress_bar()

    camera_started = False
    counter: PeopleCounter | None = None

    try:
        if args.display:
            cv2.namedWindow("IMX500 people counter", cv2.WINDOW_NORMAL)
        camera.start()
        camera_started = True

        width, height = camera.camera_configuration()["main"]["size"]
        counter = PeopleCounter((width, height))
        started = last_report = time.monotonic()
        frames = 0
        print(f"Camera: {width}x{height} | Counting line: {COUNTING_LINE}")
        print("Counting people. Press Ctrl+C to stop.")

        while True:
            request = camera.capture_request()
            try:
                metadata = request.get_metadata()
                detections = find_people(imx500, camera, metadata)
                need_frame = args.display or args.save_frame is not None
                frame = request.make_array("main") if need_frame else None
            finally:
                request.release()

            assert counter is not None
            tracks = counter.update(detections)
            if frame is not None:
                annotated = annotate_frame(frame, tracks)
                if args.save_frame is not None and detections is not None:
                    save_annotated_frame(frame, tracks, args.save_frame)
                    print(f"Saved annotated frame to {args.save_frame}")
                    args.save_frame = None
                if args.display:
                    cv2.imshow("IMX500 people counter", annotated)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break

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
        if camera_started:
            camera.stop()
        if args.display:
            cv2.destroyAllWindows()
        if counter is not None:
            print(f"Final count: {counter.status()}")


if __name__ == "__main__":
    main()
