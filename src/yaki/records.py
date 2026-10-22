
from datetime import datetime, UTC
from pathlib import Path
import random
import shutil
import threading
import time

from nicegui import app
import orjson
from orjsonl import orjsonl

class RecordsManager:
    def __init__(self, record_file: Path):
        if record_file.exists():
            bak = record_file.with_name(record_file.name + f".{time.time()}.bak")
            shutil.copy2(record_file, bak)
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
            return True
        return False

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

            total = last_record.get("total", 0)
            if last_record.get("visitors") < g.get("visitors"):
                total += g.get("visitors") - last_record.get("visitors")
            if last_record.get("correction") < g.get("correction"):
                total += g.get("correction") - last_record.get("correction")
            now = datetime.now(UTC)
            orjsonl.append(self.file, {
                        "visitors": g.get("visitors"),
                        "staff": g.get("staff_planning").get(str(now.weekday())),
                        "correction": g.get("correction"),
                        "total": total,
                        "maximum": g.get("maximum"),
                        "host": host,
                        "date": now.strftime("%d/%m/%Y"),
                        "time": now.strftime("%H:%M:%S"),
                        "timestamp": now.timestamp(),
                        "data": data
                    })

        self.notwriting.set()




server_file = Path(__file__).parent.parent.parent / "server_records.jsonl"

server = ServerRecordsManager(server_file)
