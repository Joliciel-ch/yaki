
from datetime import datetime, UTC
from pathlib import Path
import random
import threading
import time


from nicegui import app
import orjson
from orjsonl import orjsonl

server_records = Path(__file__).parent.parent.parent / "server_records.jsonl"

server_records.touch(exist_ok=True)

@dataclass
class Result:
    ins: int = 0
    outs: int = 0

class RecordsManager:
    def __init__(self, record_file):
        record_file.touch(exist_ok=True)
        self.file = record_file
        self.notwriting = threading.Event()
        self.notwriting.set()

    def get_last_record(self):
        line = b''
        with open(self.file, "rb") as f:
            for line in f:
                pass
        try:
            return orjson.loads(line)
        except orjson.JSONDecodeError:
            return {}

    def get_all_records(self) -> list[dict]:
        self.notwriting.wait(1)
        return orjsonl.load(self.file) or []

    def get_7days_records(self) -> list[dict]:
        self.notwriting.wait(1)
        return orjsonl.load(self.file) or []

    def get_all_day_records(self) -> list[dict]:
        self.notwriting.wait(1)
        return orjsonl.load(self.file) or []

class CameraRecordsManager(RecordsManager):

    def __init__(self, record_file):
        super().__init__(record_file)
        self.ins = 0
        self.outs = 0

    def create_random_record(self):
        self.ins = self.ins + random.randint(0,2)
        self.outs = self.outs + random.randint(0,2)
        orjsonl.append(self.file, {
            "ins": self.ins,
            "outs": self.outs,
            "count": self.ins-self.outs,
            "timestamp": datetime.now(UTC)
        })

    def create_record(self, ins, outs):
        if ins != self.ins or outs != self.outs:
            # t = time.perf_counter()
            self.notwriting.clear()
            self.ins = ins
            self.outs = outs
            orjsonl.append(self.file, {
                        "ins": self.ins,
                        "outs": self.outs,
                        "count": self.ins-self.outs,
                        "timestamp": datetime.now(UTC)
                    })
            self.notwriting.set()

class ServerRecordsManager(RecordsManager):

    def create_record(self, data=None, host="self"):

        self.notwriting.clear()

        g = app.storage.general.get("config", {})

        last_record = self.get_last_record()

        compare = [
            "visitors",
            "correction",
            "maximum",
            "host"
        ]

        same = True
        for c in compare:
            if last_record.get(c) != g.get(c):
                same = False

        if same:
            print("record NOT created, same data")
        else:
            now = datetime.now(UTC)
            orjsonl.append(self.file, {
                        "visitors": g.get("visitors"),
                        "staff": g.get("staff_planning").get(str(now.weekday())),
                        "correction": g.get("correction"),
                        "maximum": g.get("maximum"),
                        "host": host,
                        "timestamp": now.timestamp(),
                        "data": data
                    })

        self.notwriting.set()


cam_file = Path(__file__).parent.parent.parent / "camera_records.jsonl"

cam = CameraRecordsManager(cam_file)


server_file = Path(__file__).parent.parent.parent / "server_records.jsonl"

server = ServerRecordsManager(server_file)
