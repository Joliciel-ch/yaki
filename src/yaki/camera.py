
from pathlib import Path
import random
import threading
import time

import httpx2
import numpy as np
import orjson
from orjsonl import orjsonl
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
import supervision as sv
import uvicorn

from yaki import imx500_crossing

from yaki import config
from yaki import records

conf = config.load("camera")

json_file = Path("records.jsonl")

missing_jpg = Path(__file__).parent.parent / "missing.jpg"

server = httpx2.Client(
    base_url=f"http://{conf.get('server_host')}:{conf.get('server_port')}"
)

img = missing_jpg.read_bytes()


def send_last_record():
    headers = {"Content-type": "application/json",
            "Accept": "text/plain"}
    body = orjson.dumps(records.cam.get_last_record())
    try:
        response = server.post(
            f"/record/{conf.get('name')}", content=body, headers=headers
        )
    except Exception as e:
        print("error while sending result", e)

def process():
    if conf.get("type") == "imx500":

        imx500_conf = conf.get("imx500", {})

        def callback(ins, outs, _img):
            global img
            img = _img
            if records.cam.create_record(ins, outs):
                send_last_record()

        imx500_crossing.main_count_loop(callback,
                                        imx500_conf.get("detect_floor", 0.2),
                                        imx500_conf.get("track_timeout", 2),
                                        imx500_conf.get("track_threshold", 0.5),
                                        imx500_conf.get("confidence_threshold", 0.5),
                                        imx500_conf.get("min_consecutive_frames", 2),
                                    )

async def get_frame(request: Request):
    if img:
        return Response(img, media_type="image/jpeg")
    else:
        return Response(missing_jpg.read_bytes(),
                        media_type="image/jpeg")

async def get_display_frame(request: Request):
    arg = request.scope["query_string"].decode()
    if arg == "True":
        imx500_crossing.return_frame = True
    else:
        imx500_crossing.return_frame = False
    return JSONResponse("ok")

async def get_records(request: Request):
    return JSONResponse(records.cam.get_all_records())

async def get_region(request: Request):
    args = request.scope["query_string"].decode().split("&")
    if len(args) == 4:
        args = list(map(int, args))
        imx500_crossing.LINE_ZONE = sv.LineZone(
            start=sv.Point(x=int(args[0]), y=int(args[1])),
            end=sv.Point(x=int(args[2]), y=int(args[3])),
        )
        conf["imx500"]["COUNTING_LINE"] = [
            [args[0], args[1]], [args[2], args[3]]
        ]
        config.save("camera", conf)
        return JSONResponse("updated successfully")
    return JSONResponse([
        imx500_crossing.LINE_ZONE.vector.start.x,
        imx500_crossing.LINE_ZONE.vector.start.y,
        imx500_crossing.LINE_ZONE.vector.end.x,
        imx500_crossing.LINE_ZONE.vector.end.y
    ])

def say_hello():
    headers = {"Content-type": "application/json",
                    "Accept": "text/plain"}
    body = orjson.dumps(conf)
    status = None
    while status != 200:
        try:
            response = server.post("/hello", content=body, headers=headers)
            status = response.status_code
            print(status)
        except Exception as e:
            print(f"Error while saying hello to {server}", e)
            time.sleep(2)


process_thread = threading.Thread(target=process, daemon=True)
hello_thread = threading.Thread(target=say_hello, daemon=True)

def restart_processing(request: Request):
    global process_thread
    imx500_crossing.count_enabled = False
    process_thread.join()
    
    imx500_crossing.count_enabled = True
    process_thread = threading.Thread(target=process, daemon=True)
    process_thread.start()

app = Starlette(routes=[
    Route("/display", get_display_frame),
    Route("/frame", get_frame),
    Route("/records", get_records),
    Route("/region", get_region),
    Route("/restart", restart_processing),
])

def main(reload=False):
    records.cam.create_record(0, 0)
    hello_thread.start()
    process_thread.start()
    # threading.Thread(target=send_last_record, daemon=True).start()
    uvicorn.run(app, host=conf.get("host", "0.0.0.0"), port=conf.get("port", 8081), reload=reload, access_log=False)

if __name__ == "__main__":
    main(False)

