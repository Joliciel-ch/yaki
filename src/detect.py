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
import cv2
import numpy as np

from modlib.devices import AiCamera
from modlib.models import COLOR_FORMAT, MODEL_TYPE, Model
from modlib.models.post_processors import pp_od_yolo_ultralytics

from ultralytics.solutions import ObjectCounter


# ---------------------------------------------------------
# 1. Modèle YOLO pour IMX500 (chargé dans le processeur IA)
# ---------------------------------------------------------
class YOLO_IMX(Model):
    def __init__(self):
        super().__init__(
            model_file="yolo11n_imx_model/packerOut.zip",   # modèle converti pour IMX500
            model_type=MODEL_TYPE.CONVERTED,
            color_format=COLOR_FORMAT.RGB,
            preserve_aspect_ratio=False,
        )
        self.labels = np.genfromtxt(
            "yolo11n_imx_model/labels.txt",
            dtype=str,
            delimiter="\n"
        )

    def post_process(self, output_tensors):
        # Convertit les tenseurs IMX500 → format Ultralytics (xyxy, conf, cls)
        return pp_od_yolo_ultralytics(output_tensors)


# ---------------------------------------------------------
# 2. Initialisation IMX500
# ---------------------------------------------------------
print("init IMX500")
vcap = AiCamera(frame_rate=16)
model = YOLO_IMX()
vcap.deploy(model)   # Le modèle est chargé dans le processeur IA du IMX500

print("init ObjectCounter")
# ---------------------------------------------------------
# 3. ObjectCounter Ultralytics (réutilisé tel quel)
# ---------------------------------------------------------
region_points = [(0, 0), (0, 0)]

counter = ObjectCounter(
    show=False,
    region=region_points,
    model="yolo11n.pt",        # IMPORTANT : pas de modèle Ultralytics → on utilise IMX500
    classes=[0],       # Personnes (COCO class 0)
    verbose=False
)


# ---------------------------------------------------------
# 4. Boucle de traitement IMX500
# ---------------------------------------------------------
img = b''
results = None

def process():
    with vcap as stream:
        for frame in stream:

            # frame.image = image RGB du IMX500
            # frame.detections = liste de détections déjà calculées par le processeur IA

            # Convertir les détections IMX500 → format Ultralytics Nx6
            dets = frame.detections

            print(dets)

            if len(dets) > 0:
                xyxy = np.array([d.bbox for d in dets])
                conf = np.array([d.confidence for d in dets])
                cls = np.array([d.class_id for d in dets])

                ul_dets = np.column_stack([xyxy, conf, cls])

                # Comptage Ultralytics (sans ré-inférence)
                results = counter.process(
                    frame.image,
                    detections=ul_dets
                )

            # Encodage JPEG pour streaming / API
            _, imencode_image = cv2.imencode('.jpg', frame.image)
            img = imencode_image.tobytes()


# def process():
#     global img
#     global results
#     while vcap.isOpened():
#         success, frame = vcap.read()

#         if not success:
#             print("Video frame is empty or processing is complete.")
#             break

#         results = counter.process(frame)
#         _, imencode_image = cv2.imencode('.jpg', frame)
#         img = imencode_image.tobytes()

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
