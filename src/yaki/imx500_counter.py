#!/usr/bin/env python3

"""
IMX500 people counter
---------------------

Architecture:

    IMX500 / YOLO11n .rpk
            |
            | person detections
            v
       SimpleTracker
            |
            | persistent track IDs
            v
       PeopleCounter
            |
            v
       IN / OUT counts

Dependencies:
    - picamera2
    - numpy

NO:
    - ultralytics
    - opencv
    - scipy
    - matplotlib
    - GUI / visualization

The YOLO11n model runs on the IMX500.

Default model:
    /usr/share/imx500-models/imx500_network_yolo11n_pp.rpk

The model is expected to be the Raspberry Pi IMX500
YOLO11n post-processed model.

Person class:
    COCO class 0

Coordinates:
    The counting line is expressed in camera-output coordinates.

"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import numpy as np

from picamera2 import Picamera2
from picamera2.devices import IMX500
from picamera2.devices.imx500 import NetworkIntrinsics


# ============================================================
# CONFIGURATION
# ============================================================

MODEL = "/usr/share/imx500-models/imx500_network_yolo11n_pp.rpk"

# Detection confidence threshold.
#
# Start around 0.45-0.55.
DETECTION_THRESHOLD = 0.50

# ------------------------------------------------------------
# Counting line
# ------------------------------------------------------------
#
# Example for a 1280x720 camera:
#
# vertical line:
#       x = 640
#
COUNTING_LINE = (
    (640, 100),
    (640, 620),
)

# Direction definition:
#
# For a VERTICAL line:
#
#       OUT  <--- | --->  IN
#
# For a HORIZONTAL line:
#
#       OUT
#        ^
#        |
#        |
#       ---
#        |
#        v
#       IN
#
# Change these if your desired direction is reversed.

# ------------------------------------------------------------
# Tracker configuration
# ------------------------------------------------------------

# Maximum number of frames a track can disappear before
# being deleted.
MAX_MISSED_FRAMES = 15

# Minimum IoU for associating a detection with an existing track.
MIN_IOU = 0.10

# Maximum centroid distance as a fraction of the image
# diagonal.
#
# This prevents two nearby people from being matched just
# because their boxes happen to overlap slightly.
MAX_CENTROID_DISTANCE = 0.08

# Maximum number of simultaneously tracked people.
MAX_TRACKS = 30

# ------------------------------------------------------------
# Output frequency
# ------------------------------------------------------------

STATUS_INTERVAL = 1.0


# ============================================================
# DATA STRUCTURES
# ============================================================

@dataclass
class Detection:
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float

    @property
    def center(self):
        return (
            (self.x1 + self.x2) / 2.0,
            (self.y1 + self.y2) / 2.0,
        )

    @property
    def width(self):
        return self.x2 - self.x1

    @property
    def height(self):
        return self.y2 - self.y1


@dataclass
class Track:
    track_id: int

    x1: float
    y1: float
    x2: float
    y2: float

    confidence: float

    missed_frames: int = 0

    # Previous center.
    previous_center: Optional[tuple[float, float]] = None

    @property
    def center(self):
        return (
            (self.x1 + self.x2) / 2.0,
            (self.y1 + self.y2) / 2.0,
        )

    def update(self, detection: Detection):
        self.previous_center = self.center

        self.x1 = detection.x1
        self.y1 = detection.y1
        self.x2 = detection.x2
        self.y2 = detection.y2

        self.confidence = detection.confidence
        self.missed_frames = 0


# ============================================================
# GEOMETRY
# ============================================================

def iou(a: Track, b: Detection) -> float:
    """
    Intersection over Union between a track and detection.
    """

    x1 = max(a.x1, b.x1)
    y1 = max(a.y1, b.y1)

    x2 = min(a.x2, b.x2)
    y2 = min(a.y2, b.y2)

    intersection_width = max(0.0, x2 - x1)
    intersection_height = max(0.0, y2 - y1)

    intersection = (
        intersection_width *
        intersection_height
    )

    if intersection <= 0:
        return 0.0

    area_a = (
        max(0.0, a.x2 - a.x1) *
        max(0.0, a.y2 - a.y1)
    )

    area_b = (
        max(0.0, b.x2 - b.x1) *
        max(0.0, b.y2 - b.y1)
    )

    union = area_a + area_b - intersection

    if union <= 0:
        return 0.0

    return intersection / union


def centroid_distance(
    a: Track,
    b: Detection,
    frame_diagonal: float,
) -> float:

    ax, ay = a.center
    bx, by = b.center

    distance = (
        (ax - bx) ** 2 +
        (ay - by) ** 2
    ) ** 0.5

    if frame_diagonal <= 0:
        return 1.0

    return distance / frame_diagonal


def side_of_line(
    point: tuple[float, float],
    line_start: tuple[float, float],
    line_end: tuple[float, float],
) -> float:
    """
    Signed side of a line.

    Positive and negative indicate opposite sides.
    """

    px, py = point
    x1, y1 = line_start
    x2, y2 = line_end

    return (
        (x2 - x1) * (py - y1)
        - (y2 - y1) * (px - x1)
    )


# ============================================================
# TRACKER
# ============================================================

class SimpleTracker:
    """
    Lightweight people tracker.

    Uses:
        - IoU
        - centroid distance
        - persistent IDs
        - missed-frame timeout

    No external tracking library required.
    """

    def __init__(
        self,
        frame_width: int,
        frame_height: int,
    ):

        self.frame_width = frame_width
        self.frame_height = frame_height

        self.frame_diagonal = (
            frame_width ** 2 +
            frame_height ** 2
        ) ** 0.5

        self.tracks: list[Track] = []

        self.next_track_id = 1

    # --------------------------------------------------------
    # Update
    # --------------------------------------------------------

    def update(
        self,
        detections: list[Detection],
    ) -> list[Track]:

        if len(detections) > MAX_TRACKS:
            detections = sorted(
                detections,
                key=lambda d: d.confidence,
                reverse=True,
            )[:MAX_TRACKS]

        # No existing tracks.
        if not self.tracks:

            for detection in detections:
                self._create_track(detection)

            return self.tracks

        # ----------------------------------------------------
        # Generate possible matches.
        # ----------------------------------------------------

        candidates = []

        for track_index, track in enumerate(self.tracks):

            for detection_index, detection in enumerate(
                detections
            ):

                overlap = iou(
                    track,
                    detection,
                )

                distance = centroid_distance(
                    track,
                    detection,
                    self.frame_diagonal,
                )

                # A match is allowed if either:
                #
                #   1. boxes overlap enough
                #   2. centers are sufficiently close
                #
                if (
                    overlap >= MIN_IOU
                    or distance <= MAX_CENTROID_DISTANCE
                ):

                    # Lower is better.
                    #
                    # IoU is converted into a cost.
                    cost = (
                        (1.0 - overlap)
                        + distance
                    )

                    candidates.append(
                        (
                            cost,
                            track_index,
                            detection_index,
                        )
                    )

        candidates.sort(
            key=lambda x: x[0]
        )

        matched_tracks = set()
        matched_detections = set()

        # ----------------------------------------------------
        # Greedy assignment.
        #
        # For a people-counting camera this is generally
        # sufficient and avoids scipy/Hungarian dependencies.
        # ----------------------------------------------------

        for (
            _cost,
            track_index,
            detection_index,
        ) in candidates:

            if track_index in matched_tracks:
                continue

            if detection_index in matched_detections:
                continue

            track = self.tracks[track_index]
            detection = detections[detection_index]

            track.update(detection)

            matched_tracks.add(track_index)
            matched_detections.add(detection_index)

        # ----------------------------------------------------
        # Increase missed-frame count for unmatched tracks.
        # ----------------------------------------------------

        for index, track in enumerate(self.tracks):

            if index not in matched_tracks:
                track.missed_frames += 1

        # ----------------------------------------------------
        # Remove dead tracks.
        # ----------------------------------------------------

        self.tracks = [
            track
            for track in self.tracks
            if track.missed_frames <= MAX_MISSED_FRAMES
        ]

        # ----------------------------------------------------
        # Create tracks for unmatched detections.
        # ----------------------------------------------------

        for detection_index, detection in enumerate(
            detections
        ):

            if detection_index not in matched_detections:
                self._create_track(detection)

        return self.tracks

    # --------------------------------------------------------
    # Create track
    # --------------------------------------------------------

    def _create_track(
        self,
        detection: Detection,
    ):

        if len(self.tracks) >= MAX_TRACKS:
            return

        track = Track(
            track_id=self.next_track_id,

            x1=detection.x1,
            y1=detection.y1,
            x2=detection.x2,
            y2=detection.y2,

            confidence=detection.confidence,

            missed_frames=0,

            previous_center=None,
        )

        self.next_track_id += 1

        self.tracks.append(track)


# ============================================================
# PEOPLE COUNTER
# ============================================================

class PeopleCounter:
    """
    Counts unique tracked people crossing a line.

    Important:
        Counting is based on TRACK ID, not detections.

    Therefore:
        one person = one count
    even if they are detected for many frames.
    """

    def __init__(
        self,
        line_start: tuple[float, float],
        line_end: tuple[float, float],
    ):

        self.line_start = line_start
        self.line_end = line_end

        self.in_count = 0
        self.out_count = 0

        self.total_count = 0

        # Track IDs that have already crossed the line.
        self.counted_ids: set[int] = set()

        # Last known side of the line for each track.
        self.previous_sides: dict[int, float] = {}

    # --------------------------------------------------------
    # Update
    # --------------------------------------------------------

    def update(
        self,
        tracks: list[Track],
    ):

        active_ids = set()

        for track in tracks:

            active_ids.add(track.track_id)

            current_center = track.center

            current_side = side_of_line(
                current_center,
                self.line_start,
                self.line_end,
            )

            previous_side = self.previous_sides.get(
                track.track_id
            )

            # First frame for this track.
            if previous_side is None:

                self.previous_sides[
                    track.track_id
                ] = current_side

                continue

            # No crossing.
            if (
                previous_side == 0
                or current_side == 0
                or (
                    previous_side > 0
                    and current_side > 0
                )
                or (
                    previous_side < 0
                    and current_side < 0
                )
            ):

                self.previous_sides[
                    track.track_id
                ] = current_side

                continue

            # ------------------------------------------------
            # The object crossed the line.
            # ------------------------------------------------

            if track.track_id not in self.counted_ids:

                direction = self._direction(
                    previous_side,
                    current_side,
                )

                if direction == "IN":
                    self.in_count += 1

                else:
                    self.out_count += 1

                self.total_count += 1

                self.counted_ids.add(
                    track.track_id
                )

                print(
                    f"PERSON {track.track_id}: "
                    f"{direction} | "
                    f"IN={self.in_count} "
                    f"OUT={self.out_count}"
                )

            self.previous_sides[
                track.track_id
            ] = current_side

        # ----------------------------------------------------
        # Remove old track state.
        #
        # This prevents dictionaries growing forever.
        # ----------------------------------------------------

        old_ids = (
            set(self.previous_sides)
            - active_ids
        )

        for track_id in old_ids:

            del self.previous_sides[
                track_id
            ]

    # --------------------------------------------------------
    # Direction
    # --------------------------------------------------------

    @staticmethod
    def _direction(
        previous_side: float,
        current_side: float,
    ) -> str:

        # The exact direction depends on the orientation
        # of the line.
        #
        # We use the signed transition here:
        #
        # negative -> positive = IN
        # positive -> negative = OUT

        if (
            previous_side < 0
            and current_side > 0
        ):
            return "IN"

        return "OUT"

    # --------------------------------------------------------
    # Status
    # --------------------------------------------------------

    def status(self) -> dict:

        return {
            "in": self.in_count,
            "out": self.out_count,
            "total": self.total_count,
        }


# ============================================================
# IMX500 DETECTION
# ============================================================

class IMX500PeopleDetector:
    """
    Reads YOLO11n post-processed detections from IMX500.

    The official Raspberry Pi YOLO11n PP model outputs:
        boxes
        scores
        classes

    We keep only:
        COCO class 0 = person
    """

    PERSON_CLASS = 0

    def __init__(
        self,
        imx500: IMX500,
        picam2: Picamera2,
        threshold: float,
    ):

        self.imx500 = imx500
        self.picam2 = picam2
        self.threshold = threshold

        self.intrinsics = (
            imx500.network_intrinsics
        )

        if self.intrinsics is None:

            self.intrinsics = NetworkIntrinsics()

            self.intrinsics.task = (
                "object detection"
            )

        if self.intrinsics.task != (
            "object detection"
        ):

            raise RuntimeError(
                "The IMX500 model is not configured "
                "as an object-detection network."
            )

        self.intrinsics.update_with_defaults()

    # --------------------------------------------------------
    # Get detections
    # --------------------------------------------------------

    def get_detections(
        self,
        metadata: dict,
    ) -> list[Detection]:

        outputs = self.imx500.get_outputs(
            metadata,
            add_batch=True,
        )

        if outputs is None:
            return []

        # For the official YOLO11n PP RPK:
        #
        # outputs[0] = boxes
        # outputs[1] = scores
        # outputs[2] = classes
        #
        boxes = np.asarray(
            outputs[0][0]
        )

        scores = np.asarray(
            outputs[1][0]
        )

        classes = np.asarray(
            outputs[2][0]
        )

        # ----------------------------------------------------
        # Apply confidence + person filter.
        # ----------------------------------------------------

        detections = []

        for box, score, category in zip(
            boxes,
            scores,
            classes,
        ):

            score = float(score)
            category = int(category)

            if score < self.threshold:
                continue

            if category != self.PERSON_CLASS:
                continue

            # ------------------------------------------------
            # The official YOLO11n PP model is normally run
            # with:
            #
            #   --bbox-normalization
            #   --bbox-order xy
            #
            # so normalize/order the coordinates exactly as
            # the official Picamera2 example does.
            # ------------------------------------------------

            box = np.asarray(
                box,
                dtype=np.float32,
            )

            input_width, input_height = (
                self.imx500.get_input_size()
            )

            # YOLO11n PP model's bounding boxes are
            # normalized in the model-input coordinate system.
            #
            # Official Raspberry Pi demo uses bbox normalization
            # and xy ordering for this model.
            box = box / input_height

            # Convert yx -> xy ordering.
            box = box[
                [1, 0, 3, 2]
            ]

            # Convert model coordinates to camera
            # output coordinates.
            box = (
                self.imx500.convert_inference_coords(
                    box,
                    metadata,
                    self.picam2,
                )
            )

            x, y, w, h = [
                float(v)
                for v in box
            ]

            detection = Detection(
                x1=x,
                y1=y,
                x2=x + w,
                y2=y + h,
                confidence=score,
            )

            detections.append(
                detection
            )

        return detections


# ============================================================
# CAMERA
# ============================================================

def create_camera(
    model_path: str,
):

    # IMPORTANT:
    #
    # IMX500 must be instantiated BEFORE Picamera2.
    #
    imx500 = IMX500(
        model_path
    )

    intrinsics = (
        imx500.network_intrinsics
    )

    if intrinsics is None:

        intrinsics = NetworkIntrinsics()

        intrinsics.task = (
            "object detection"
        )

    elif intrinsics.task != (
        "object detection"
    ):

        raise RuntimeError(
            f"Model task is "
            f"{intrinsics.task!r}, "
            f"not object detection."
        )

    intrinsics.update_with_defaults()

    picam2 = Picamera2(
        imx500.camera_num
    )

    config = (
        picam2
        .create_preview_configuration(
            controls={
                "FrameRate":
                    intrinsics.inference_rate
            },
            buffer_count=12,
        )
    )

    picam2.configure(
        config
    )

    return (
        imx500,
        picam2,
        intrinsics,
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("==========================================")
    print(" IMX500 PEOPLE COUNTER")
    print("==========================================")
    print()
    print(
        f"Model: {MODEL}"
    )
    print(
        "Detector: IMX500 YOLO11n"
    )
    print(
        "Class: person (0)"
    )
    print(
        "Tracker: IoU + centroid"
    )
    print(
        "Visualization: disabled"
    )
    print()

    # --------------------------------------------------------
    # Camera / IMX500
    # --------------------------------------------------------

    (
        imx500,
        picam2,
        intrinsics,
    ) = create_camera(
        MODEL
    )

    print(
        "Loading IMX500 network..."
    )

    imx500.show_network_fw_progress_bar()

    # --------------------------------------------------------
    # Start camera
    # --------------------------------------------------------

    picam2.start()

    # --------------------------------------------------------
    # Detector
    # --------------------------------------------------------

    detector = (
        IMX500PeopleDetector(
            imx500=imx500,
            picam2=picam2,
            threshold=DETECTION_THRESHOLD,
        )
    )

    # --------------------------------------------------------
    # Determine actual camera output dimensions.
    # --------------------------------------------------------

    camera_config = (
        picam2.camera_configuration()
    )

    main_stream = camera_config[
        "main"
    ]

    frame_width, frame_height = (
        main_stream["size"]
    )

    print(
        f"Camera: "
        f"{frame_width}x{frame_height}"
    )

    print(
        f"Counting line: "
        f"{COUNTING_LINE}"
    )

    # --------------------------------------------------------
    # Tracker
    # --------------------------------------------------------

    tracker = SimpleTracker(
        frame_width=frame_width,
        frame_height=frame_height,
    )

    # --------------------------------------------------------
    # Counter
    # --------------------------------------------------------

    counter = PeopleCounter(
        line_start=COUNTING_LINE[0],
        line_end=COUNTING_LINE[1],
    )

    # --------------------------------------------------------
    # Runtime statistics
    # --------------------------------------------------------

    last_status = time.monotonic()

    frames = 0

    fps_start = time.monotonic()

    print()
    print(
        "Running."
    )
    print(
        "Press Ctrl+C to stop."
    )
    print()

    # --------------------------------------------------------
    # Main loop
    # --------------------------------------------------------

    try:

        while True:

            # ------------------------------------------------
            # Capture metadata only.
            #
            # We deliberately do NOT capture an image.
            #
            # The IMX500 has already performed inference.
            # ------------------------------------------------

            metadata = (
                picam2.capture_metadata()
            )

            # ------------------------------------------------
            # IMX500 → person detections
            # ------------------------------------------------

            detections = (
                detector.get_detections(
                    metadata
                )
            )

            # ------------------------------------------------
            # Detections → tracks
            # ------------------------------------------------

            tracks = tracker.update(
                detections
            )

            # ------------------------------------------------
            # Tracks → counting
            # ------------------------------------------------

            counter.update(
                tracks
            )

            frames += 1

            # ------------------------------------------------
            # Status
            # ------------------------------------------------

            now = time.monotonic()

            if (
                now - last_status
                >= STATUS_INTERVAL
            ):

                elapsed = (
                    now - fps_start
                )

                fps = (
                    frames / elapsed
                    if elapsed > 0
                    else 0.0
                )

                status = (
                    counter.status()
                )

                print(
                    f"FPS={fps:5.1f} | "
                    f"tracks={len(tracks):2d} | "
                    f"IN={status['in']:4d} | "
                    f"OUT={status['out']:4d} | "
                    f"TOTAL={status['total']:4d}"
                )

                last_status = now

    except KeyboardInterrupt:

        print()
        print(
            "Stopping..."
        )

    finally:

        picam2.stop()

        print()
        print(
            "Final count:"
        )
        print(
            counter.status()
        )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
