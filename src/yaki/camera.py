
from pathlib import Path
import random
import threading
import time

import httpx2
import orjson
from orjsonl import orjsonl
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from ultralytics import YOLO, solutions
from ultralytics.solutions.solutions import SolutionResults
import uvicorn

from yaki import config
from yaki import records

conf = config.load("camera")

json_file = Path("records.jsonl")

missing_jpg = Path(__file__).parent.parent / "missing.jpg"

img = missing_jpg.read_bytes()

server = httpx2.Client(
    base_url=f"http://{conf.get('server_host')}:{conf.get('server_port')}"
)


def send_last_record():
    while True:
        
        headers = {"Content-type": "application/json",
                "Accept": "text/plain"}
        body = orjson.dumps(records.cam.get_last_record())
        try:
            response = server.post(
                f"/record/{conf.get('name')}", content=body, headers=headers
            )
        except Exception as e:
            print("error while sending results", e)
        time.sleep(1)

def process():
    global img
    if conf.get("camera") == "laptop":
        import cv2

        vcap = cv2.VideoCapture(0)
        #video_capture = cv2.VideoCapture("testok.mp4")
        width  = vcap.get(cv2.CAP_PROP_FRAME_WIDTH)   # float `width`
        height = vcap.get(cv2.CAP_PROP_FRAME_HEIGHT)  # float `height`

        region_points = [(0, 0), (width, 0), (width, height), (0, height)]
        counter = solutions.RegionCounter(
                    # show=False, 
                    region=region_points, 
                    model="yolo11n.pt",
                    classes=[0],
                    
                    verbose=False,
                )
        
        while vcap.isOpened():
            success, frame = vcap.read()

            if not success:
                print("Video frame is empty or processing is complete.")
                break

            result = counter.process(frame)
            # counter.forget_tracks()
            records.cam.create_record(result)
            _, imencode_image = cv2.imencode('.jpg', frame)
            img = imencode_image.tobytes()

async def get_frame(request: Request):
    if img:
        return Response(img, media_type="image/jpeg")
    else:
        return Response( missing_jpg.read_bytes(), 
                        media_type="image/jpeg")

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

def say_hello():
    headers = {"Content-type": "application/json",
                    "Accept": "text/plain"}
    body = orjson.dumps(conf)
    status = None
    while status != 200:
        try:
            response = server.post("/hello", content=body, headers=headers)
            status = response.status_code
        except Exception as e:
            print(f"Error while saying hello to {server}", e)
            time.sleep(2)

app = Starlette(routes=[
    Route("/frame", get_frame),
    Route("/results", get_results),
    Route("/region", get_region),
])


def main(reload=False):
    say_hello()
    threading.Thread(target=process, daemon=True).start()
    threading.Thread(target=send_last_record, daemon=True).start()
    uvicorn.run(app, host=conf.get("host", "0.0.0.0"), port=conf.get("port", 8081), reload=reload, access_log=False)

if __name__ == "__main__":
    main(True)
