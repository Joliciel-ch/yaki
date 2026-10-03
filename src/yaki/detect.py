#!/usr/bin/env python3
import base64
import json
import signal
import threading
import time

import cv2
import numpy as np
from ultralytics import YOLO, solutions

import http.server
import socketserver

ADDRESS = "0.0.0.0"
PORT = 8081
import cv2
import numpy as np

from ultralytics.solutions import ObjectCounter

from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import FfmpegOutput

img = b''
results =  {}

# 1. Initialize Picamera2
vcap = Picamera2()

# 2. Configure video stream (OpenCV reads BGR, but picamera2 generates RGB888 natively)
#    We will set up an RGB888 profile and convert it down inside the read helper.
width, height = 640, 480
config = vcap.create_video_configuration(main={"size": (1280, 720), "format": "RGB888"})
#picam2.preview_configuration.main.size = (1280, 720)
#picam2.preview_configuration.main.format = "RGB888"
#picam2.preview_configuration.align()
#picam2.configure("preview")
#picam2.start()
print(config)
vcap.configure(config)

# 3. Start the camera hardware stream
vcap.start()
out = False
fourcc = cv2.VideoWriter_fourcc(*'XVID')

# 4. Helper function to mimic vcap.read()
def read_frame(camera_instance):
    global start_rec
    global recording
    global stop_rec
    global out
    try:
        # Capture the raw frame as a numpy array from the running stream
        frame = camera_instance.capture_array()

        return True, frame
    except Exception as e:
        print(f"Error capturing frame: {e}")
        return False, None

print("Camera stream active. Press 'q' to stop.")

region_points = [(0, 0), (0, 0)]

counter = ObjectCounter(
    show=False,
    region=region_points,
    model="yolo11n.pt",  
    imgsz=(1280, 720),
    #classes=[0],    
    verbose=False
)

def process():
    global img
    global results
    while True:
        success, frame = read_frame(vcap)

        if not success:
            print("Video frame is empty or processing is complete.")
            break

        results = counter.process(frame)
        ok, imencode_image = cv2.imencode('.jpg', frame)
        if ok:
            img = imencode_image.tobytes()

class RequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        global start_rec
        global stop_rec
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        uri = self.path.split('?')
        path = uri[0]
        body = json.dumps("nobody").encode("utf-8")

        if path == "/frame":
            self.send_header('Content-type', 'image/jpeg')
            
            body = img or b''
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

        elif path == "/rec/start":
            encoder = H264Encoder(10000000)
            output = FfmpegOutput(f'{time.time()}.mp4')

            vcap.start_recording(encoder, output)

            body = json.dumps("started").encode("utf-8")

        elif path == "/rec/stop":
            vcap.stop_recording()

            body = json.dumps("stopped").encode("utf-8")


        self.send_header("Content-Length", str(len(body)))
        self.end_headers()

        self.wfile.write(body)

def run():
    try:
        threading.Thread(target=process, daemon=True).start()
        server = socketserver.TCPServer((ADDRESS, PORT), RequestHandler)
        
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCtrl-C received, shutting down...")
        server.shutdown()   # clean exit
        server.server_close()

if __name__ == "__main__":
    run()
