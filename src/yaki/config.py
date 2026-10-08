
import copy
from pathlib import Path

from nicegui import app
import orjson

default_config = {
    "camera": {
        "host": "127.0.0.1",
        "port": 8081,
        "server_host": "127.0.0.1",
        "server_port": 8080,
        "camera": "imx500",
        "name": "local",
        "imx500": {
            "MODEL": "/usr/share/imx500-models/imx500_network_yolo11n_pp.rpk",
            "CONFIDENCE_THRESHOLD": 0.6,
            "TRACKING_FLOOR": 0.20,
            "COUNTING_LINE": ((0, 0), (100, 100)),
            "TRACK_TIMEOUT": 2.0,
            "STATUS_INTERVAL": 1.0,
            "PERSON_CLASS": 0,
            "WIDTH": 1280,
            "HEIGHT": 720,
        }
    },
    "server": {
        "visitors": 0,
        "staff_planning": { f"{i}": 20 for i in range(7) },
        "correction": 0,
        "maximum": 100,
        "caution_%": 80,
        "alert_%": 90,
        "opening_time": "10:00",
        "closing_time": "19:00",
        "update_region_points": [ [0, 0], [0, 0] ],
        "clients": {}
    }
}

config_file = Path(__file__).parent.parent.parent / "config.json"

config_file.touch(exist_ok=True)

def load(key = "server"):
    default = copy.deepcopy(default_config).get(key, {})
    cfg = config_file.read_bytes()
    if len(cfg) > 0:
        default.update(orjson.loads(config_file.read_bytes()).get(key, {}))
    return default

def init(key="server"):
    app.storage.general["config"] = default_config.get(key)
    app.storage.general["config"].update(load(key))

def save(key="server", data=None):
    config_json = {}
    config_bytes = config_file.read_bytes()
    if len(config_bytes) > 0:
        config_json = orjson.loads(config_file.read_bytes())
    if data:
        config_json[key].update(data)
    else:
        config_json[key] = app.storage.general.get("config", {})
    config_file.write_bytes(orjson.dumps(config_json, option=orjson.OPT_INDENT_2))
