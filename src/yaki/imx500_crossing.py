#!/usr/bin/env python3
"""Count people crossing a line using IMX500 detections and Supervision."""

from __future__ import annotations

import pprint
import time
from pathlib import Path
from typing import Any
import json

import cv2
import numpy as np
import supervision as sv
from picamera2 import Picamera2
from picamera2.controls import Controls
from picamera2.devices import IMX500
from picamera2.devices.imx500 import NetworkIntrinsics
from picamera2.encoders import H264Encoder
from picamera2.outputs import FfmpegOutput
from trackers import ByteTrackTracker

from yaki import config

encoder = H264Encoder(bitrate=6000000, profile="high")

conf = config.load("camera")

conf.update({ "recording": False })

PERSON_CLASS = 0

LINE_ZONE = sv.LineZone(
    start=sv.Point(x=0, y=0),
    end=sv.Point(x=1, y=1),
)

def new_zone():
    global LINE_ZONE
    l = conf.get("imx500.line_pos", [[0, 0], [100, 100]])

    if not (LINE_ZONE.vector.start.x == l[0][0] and \
        LINE_ZONE.vector.start.y == l[0][1] and \
        LINE_ZONE.vector.end.x == l[1][0] and \
        LINE_ZONE.vector.end.y == l[1][1]):

        LINE_ZONE = sv.LineZone(
            start=sv.Point(x=int(l[0][0]), y=int(l[0][1])),
            end=sv.Point(x=int(l[1][0]), y=int(l[1][1])),
        )

new_zone()

box_annotator = sv.BoxAnnotator()
label_annotator = sv.LabelAnnotator()
line_annotator = sv.LineZoneAnnotator()

missing_jpg = Path(__file__).parent.parent / "missing.jpg"

def gen_controls(config):
    keys = [ k for k in config.keys() if k.startswith("controls.") ]
    return { k.split(".")[1]: config.get(k) for k in keys}

def create_camera(
    capture_images: bool = False,
) -> tuple[IMX500, Picamera2]:
    imx500 = IMX500(conf.get("imx500.model"))
    
    camera = Picamera2(imx500.camera_num)

    preview_options = {
        "main": { "size": (conf.get("imx500.width"), conf.get("imx500.height")), "format": "RGB888" },
        #"controls": {"FrameRate": conf.get("imx500.fps")},
        "buffer_count": 6,
    }

    camera.configure(camera.create_preview_configuration(**preview_options))

    for k, v in sorted(camera.camera_controls.items()):
        print(f"{k}:")
        print(f"    min={v[0]}")
        print(f"    max={v[1]}")
        print(f"    default={v[2]}")

    print("fps config", conf.get("imx500.fps"))
        
    return imx500, camera


def update_config():
    global conf
    conf = config.load("camera")
    
    ctrls = gen_controls(conf)
    print(ctrls)
    try:
        camera.set_controls(ctrls)
    except Exception as e:
        print("Error while setting controls", e)
    
    new_zone()

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

imx500, camera = create_camera()

def main_count_loop(callback) -> None:
    imx500.show_network_fw_progress_bar()

    rec_flag = False
    rec_time = 0

    writer = None

    while not camera.started:
        try:
            camera.start()
        except Exception as e:
            print(e)
            time.sleep(2)

    tracker = ByteTrackTracker(
        lost_track_buffer=round(conf.get("imx500.track_timeout", 2) * conf.get("imx500.fps")),
        frame_rate=conf.get("imx500.fps"),
        track_activation_threshold=conf.get("imx500.track_threshold", 0.35),
        minimum_consecutive_frames=conf.get("imx500.min_consecutive_frames", 1),
        high_conf_det_threshold=conf.get("imx500.confidence_thresold", 0.5),
    )

    #frame_count = 0
    #inf_count = 0
    #start_time = time.monotonic()
    #elapsed = 0
    #inf_elapsed = 0
    while camera.is_open and conf.get("imx500.enabled"):
        #frame_count += 1
        #elapsed = time.monotonic() - start_time
        #t0 = time.perf_counter()
        request = camera.capture_request()
        frame = None
        try:
            metadata = request.get_metadata()
            detections = find_people(imx500, camera, metadata, conf.get("imx500.detect_floor", 0.2))
            
            if conf.get("display_frame") or conf.get("recording"):
                frame = request.make_array("main")
        finally:
            request.release()

        #t1 = time.perf_counter()
        #t2 = time.perf_counter()
        if detections is not None:
            #inf_count += 1
            #for confidence in detections.confidence:
            #    print(confidence)
            tracked = tracker.update(detections)
            LINE_ZONE.trigger(tracked)

            if conf.get("display_frame") or conf.get("recording"):
                frame = annotate_frame(
                    frame,
                    detections,
                    tracked,
                    LINE_ZONE
                )
                if writer is not None:
                    writer.write(frame)

                _, frame = cv2.imencode('.jpg', frame)

                frame = frame.tobytes()
            else:
                frame = None
            #t2 = time.perf_counter()
            callback(LINE_ZONE.in_count, LINE_ZONE.out_count, frame)
            #inf_elapsed = time.monotonic() - start_time
        
        #t3 = time.perf_counter()

        #print(
        #    f"tracker={(t2-t1)*1000:.1f}ms "
        #    f"line={(t3-t2)*1000:.1f}ms "
        #    f"total={(t3-t0)*1000:.1f}ms "
        #)

        if rec_flag is False and conf.get("recording") is True:
            output = FfmpegOutput(f"cleanrec-{time.strftime("%Y-%m-%d-%H%M%S")}.mp4")
            camera.start_encoder(encoder, output)
            writer = cv2.VideoWriter(
                f"trackrec-{time.strftime("%Y-%m-%d-%H%M%S")}.mp4",
                cv2.VideoWriter_fourcc(*"mp4v"),
                conf.get("imx500.fps"),
                (1920, 1080)
            )

            rec_time = time.time()
        elif rec_flag is True and conf.get("recording") is False:
            camera.stop_encoder()
            if writer:
                writer.release()
                writer = None
        elif time.time() - rec_time > 600:
            camera.stop_encoder()
            if writer:
                writer.release()
                writer = None
            conf.update({ "recording": False })

        rec_flag = conf.get("recording")

        #if elapsed > 10:
        #    print(f"cam fps: {(frame_count / elapsed):.2f}")
        #
        #if inf_elapsed > 10:
        #    print(f"inf fps: {(inf_count / inf_elapsed):.2f}")
        

    camera.close()
