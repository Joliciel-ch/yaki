
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

records_file = Path(__file__).parent.parent.parent / "camera_records.jsonl"

cam_records = records.CameraRecordsManager(records_file)

missing_jpg = Path(__file__).parent.parent / "missing.jpg"

server = httpx2.Client(
    base_url=f"http://{conf.get('server_host')}:{conf.get('server_port')}"
)

img = missing_jpg.read_bytes()

def send_last_record():
    headers = {"Content-type": "application/json",
            "Accept": "text/plain"}
    body = orjson.dumps(cam_records.get_last_record())
    try:
        response = server.post(
            f"/record/{conf.get('name')}", content=body, headers=headers
        )
    except Exception as e:
        print("error while sending result", e)

def process():
    if conf.get("type") == "imx500":

        def callback(ins, outs, _img):
            global img
            img = _img
            if cam_records.create_record(ins, outs):
                send_last_record()

        imx500_crossing.main_count_loop(callback)

async def get_frame(request: Request):
    if img:
        return Response(img, media_type="image/jpeg")
    else:
        return Response(missing_jpg.read_bytes(),
                        media_type="image/jpeg")

async def toggle_frame_processing(request: Request):
    arg = request.scope["query_string"].decode()
    if arg == "True":
        imx500_crossing.return_frame = True
    else:
        imx500_crossing.return_frame = False
    return JSONResponse("ok")

async def all_records(request: Request):
    return JSONResponse(cam_records.get_all_records())

async def cam_config(request: Request):
    global conf
    try:
        new_settings = await request.json()
    except Exception:
        new_settings = False
    
    if new_settings:
        conf = conf | new_settings
        
        config.save("camera", conf)
        
        if conf.get("type") == "imx500":
            imx500_crossing.update_config()

    return JSONResponse(conf)

    #if "controls" in settings;

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
            print(f"Error: Cannot reach server ({server.base_url})")
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
    Route("/display", toggle_frame_processing),
    Route("/frame", get_frame),
    Route("/records", all_records),
    Route("/restart", restart_processing),
    Route("/config", cam_config, methods=["GET", "POST"]),
])

def main(reload=False):
    cam_records.create_record(0, 0)
    hello_thread.start()
    process_thread.start()
    # threading.Thread(target=send_last_record, daemon=True).start()
    uvicorn.run(app, host=conf.get("host", "0.0.0.0"), port=conf.get("port", 8081), reload=reload, access_log=False)

if __name__ == "__main__":
    main(False)

