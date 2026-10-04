#!/usr/bin/env python3
"""Print the number of people detected in each IMX500 camera frame."""

import time

from picamera2 import Picamera2
from picamera2.devices import IMX500
from picamera2.devices.imx500 import NetworkIntrinsics

MODEL = "/usr/share/imx500-models/imx500_network_yolo11n_pp.rpk"
PERSON_CLASS = 0
CONFIDENCE_THRESHOLD = 0.50
STATUS_INTERVAL = 1.0


def count_people(imx500: IMX500, metadata: dict) -> int:
    outputs = imx500.get_outputs(metadata, add_batch=True)
    if outputs is None:
        return 0

    scores = outputs[1][0]
    classes = outputs[2][0]
    return sum(
        float(score) >= CONFIDENCE_THRESHOLD and int(category) == PERSON_CLASS
        for score, category in zip(scores, classes)
    )


def main() -> None:
    # Initialize IMX500 before Picamera2 so the correct camera is selected.
    imx500 = IMX500(MODEL)
    intrinsics = imx500.network_intrinsics

    if intrinsics is None:
        intrinsics = NetworkIntrinsics()
        intrinsics.task = "object detection"
    elif intrinsics.task != "object detection":
        raise RuntimeError(f"Expected an object-detection model, got {intrinsics.task!r}")

    intrinsics.update_with_defaults()

    picam2 = Picamera2(imx500.camera_num)
    config = picam2.create_preview_configuration(
        controls={"FrameRate": intrinsics.inference_rate},
        buffer_count=12,
    )
    picam2.configure(config)

    print(f"Loading IMX500 model: {MODEL}")
    imx500.show_network_fw_progress_bar()
    picam2.start()
    print("Counting people. Press Ctrl+C to stop.")

    last_report = time.monotonic()
    try:
        while True:
            metadata = picam2.capture_metadata()
            people = count_people(imx500, metadata)

            now = time.monotonic()
            if now - last_report >= STATUS_INTERVAL:
                print(f"People in frame: {people}")
                last_report = now
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        picam2.stop()


if __name__ == "__main__":
    main()
