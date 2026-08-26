#!/usr/bin/env python3
import base64
import json
import signal
import threading

import cv2
import numpy as np
from ultralytics import YOLO, solutions

import http.server
import socketserver

ADDRESS = "0.0.0.0"
PORT = 8008

region_points = [(0, 0), (0, 0)]
# Initialize object counter object

counter = solutions.ObjectCounter(
    show=False,  # display the output
    region=region_points,  # pass region points
    model="yolo11n.pt", #"yolo11m-visdrone.pt",  # model="yolo26n-obb.pt" for object counting with OBB model.
    classes=[0],  # count specific classes, e.g., person and car with the COCO pretrained model.
    # conf= 0.3,
    # iou = 0.5,
    # agnostic_nms=True,
    #augment=True,
    # stream=True,
    # show_in = True,
    # show_out = True
    verbose=False,
    # tracker="botsort.yaml",  # choose trackers, e.g., "bytetrack.yaml"
)


# OpenCV is used to access the webcam.
vcap = cv2.VideoCapture(0)
#video_capture = cv2.VideoCapture("testok.mp4")
width  = vcap.get(cv2.CAP_PROP_FRAME_WIDTH)   # float `width`
height = vcap.get(cv2.CAP_PROP_FRAME_HEIGHT)  # float `height`

img = b''

results = None

def process():
    global img
    global results
    while vcap.isOpened():
        success, frame = vcap.read()

        if not success:
            print("Video frame is empty or processing is complete.")
            break

        results = counter.process(frame)
        _, imencode_image = cv2.imencode('.jpg', frame)
        img = imencode_image.tobytes()

class RequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        uri = self.path.split('?')
        path = uri[0]
        body = json.dumps("nobody").encode("utf-8")

        if path == "/frame":
            self.send_header('Content-type', 'image/jpeg')
            
            body = img
        elif path == "/results":
            payload = "no results"
            if results:
                payload = {
                    "ins": results.in_count,
                    "outs": results.out_count
                }
            
            body = json.dumps(payload).encode("utf-8")

        elif path == "/region":
            if len(uri) > 1:
                args = uri[1].split('&')
                if len(args) == 4:
                    print(args)
                    args = list(map(int, args))
                    counter.region = [( args[0], args[1] ), ( args[2], args[3] )]
                    counter.region_initialized = False
                    body = json.dumps("ok").encode("utf-8")


        self.send_header("Content-Length", str(len(body)))
        self.end_headers()

        self.wfile.write(body)

def run():
    threading.Thread(target=process, daemon=True).start()
    server = socketserver.TCPServer((ADDRESS, PORT), RequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCtrl-C received, shutting down...")
        server.shutdown()   # clean exit
        server.server_close()

if __name__ == "__main__":
    run()
