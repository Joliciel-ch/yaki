
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
    if conf.get("camera") == "laptop":

        def callback(ins, outs, _img):
            global img
            img = _img
            records.cam.create_record(ins, outs)

        imx500_crossing.process(callback)

async def get_frame(request: Request):
    if img:
        return Response(img, media_type="image/jpeg")
    else:
        return Response( missing_jpg.read_bytes(), 
                        media_type="image/jpeg")

async def get_display(request: Request):
    imx500_crossing.display_frame = not imx500_crossing.display_frame
    return JSONResponse("ok")

async def get_results(request: Request):
    payload = "no results"
    # if last_result:
    #     payload = {
    #         "ins": last_result.in_count,
    #         "outs": last_result.out_count,
    #     }
    return JSONResponse(payload)

async def get_region(request: Request):
    args = request.scope["query_string"].decode().split("&")
    v = imx500_crossing.LINE_ZONE.vector
    if len(args) == 4:
        args = list(map(int, args))
        v.start.x = args[0]
        v.start.y = args[1]
        v.end.x = args[2]
        v.end.y = args[3]
        return JSONResponse("updated successfully")
    return JSONResponse([
        v.start.x,
        v.start.y,
        v.end.x,
        v.end.y
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
        except Exception as e:
            print(f"Error while saying hello to {server}", e)
            time.sleep(2)

app = Starlette(routes=[
    Route("/display", get_display),
    Route("/frame", get_frame),
    Route("/results", get_results),
    Route("/region", get_region),
])


def main(reload=False):
    threading.Thread(target=say_hello, daemon=True).start()
    threading.Thread(target=process, daemon=True).start()
    # threading.Thread(target=send_last_record, daemon=True).start()
    uvicorn.run(app, host=conf.get("host", "0.0.0.0"), port=conf.get("port", 8081), reload=reload, access_log=False)

if __name__ == "__main__":
    main(True)

