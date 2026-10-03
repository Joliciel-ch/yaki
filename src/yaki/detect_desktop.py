#!/usr/bin/env python3
import base64
import json
import math
from pathlib import Path
import random
import signal
import threading
import time
from urllib.parse import urlencode

import cv2
import httpx2
import numpy as np
import orjson
import orjsonl
import uvicorn
from ultralytics import YOLO, solutions
from ultralytics.solutions.solutions import SolutionResults
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

ADDRESS = "0.0.0.0"
PORT = 8081

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

# import sqlite3
# con = sqlite3.connect("tutorial.db", check_same_thread=False)
# cur = con.cursor()
# try:
#     cur.execute("CREATE TABLE results(ins, outs)")
# except Exception as e:
#     print(e)

config_file = Path("config.json")
json_file = Path("results.jsonl")

if not json_file.exists():
    json_file.touch()

config = orjson.loads(config_file.read_bytes())["local_client"]

# OpenCV is used to access the webcam.
vcap = cv2.VideoCapture(0)
#video_capture = cv2.VideoCapture("testok.mp4")
width  = vcap.get(cv2.CAP_PROP_FRAME_WIDTH)   # float `width`
height = vcap.get(cv2.CAP_PROP_FRAME_HEIGHT)  # float `height`

img = b''

server = httpx2.Client(
    base_url=f"http://{config['server_addr']}:{config['server_port']}"
)

last_result: SolutionResults = SolutionResults()

def create_record(results: SolutionResults):
    return {
        "ins": results.in_count,
        "outs": results.out_count,
        "tracks": results.total_tracks,
        "timestamp": time.time()
    }

def record_result(result):
    if result.in_count != last_result.in_count or result.out_count != last_result.out_count:
        # t = time.perf_counter()
        orjsonl.append(json_file, create_record(result))
            # cur = con.cursor()
            # cur.executemany("INSERT INTO results VALUES(?, ?)", [transform_results(result)])
        # con.commit()
        # print("took", (time.perf_counter() - t) * 1000)

def send_result():
    ins = 1
    outs = 1
    while True:
        ins = ins + random.randint(0,2)
        outs = outs + random.randint(0,2)
        orjsonl.append(json_file, {
            "ins": ins,
            "outs": outs,
            "count": ins-outs,
            "timestamp": time.time()
        })
        headers = {"Content-type": "application/json",
                "Accept": "text/plain"}
        body = orjson.dumps(orjsonl.orjsonl.load(json_file)[-1])
        try:
            response = server.post(
                f"/record/{config['name']}", content=body, headers=headers
            )
            print("status", response.status_code)
        except Exception as e:
            print("error while sending results", e)
        time.sleep(1)

def say_hello():
    headers = {"Content-type": "application/json",
                    "Accept": "text/plain"}
    body = orjson.dumps(config)
    status = None
    while status != 200:
        try:
            print("hello")
            response = server.post("/hello", content=body, headers=headers)
            status = response.status_code
        except Exception as e:
            print("Error while saying hello", e)
            time.sleep(2)

def process():
    global img
    global last_result
    while vcap.isOpened():
        success, frame = vcap.read()

        if not success:
            print("Video frame is empty or processing is complete.")
            break

        r = counter.process(frame)
        # counter.forget_tracks()
        record_result(r)
        last_result = r
        _, imencode_image = cv2.imencode('.jpg', frame)
        img = imencode_image.tobytes()

async def get_frame(request: Request):
    return Response(img, media_type="image/jpeg")

async def get_results(request: Request):
    payload = "no results"
    if last_result:
        payload = {
            "ins": last_result.in_count,
            "outs": last_result.out_count,
        }
    return JSONResponse(payload)


async def get_region(request: Request):
    args = request.scope["query_string"].decode().split("&")
    if len(args) == 4:
        args = list(map(int, args))
        counter.region = [(args[0], args[1]), (args[2], args[3])]
        counter.region_initialized = False
        return JSONResponse("ok")
    return JSONResponse("nobody")


app = Starlette(routes=[
    Route("/frame", get_frame),
    Route("/results", get_results),
    Route("/region", get_region),
])

def run():
    say_hello()
    threading.Thread(target=process, daemon=True).start()
    threading.Thread(target=send_result, daemon=True).start()
    uvicorn.run(app, host=ADDRESS, port=PORT)

if __name__ == "__main__":
    run()
