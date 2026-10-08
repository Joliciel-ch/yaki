
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
        "camera": "laptop",
        "name": "local",
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
        "update_region_points": [ [0, 0], [0, 0] ]
    }
}

config_file = Path(__file__).parent.parent.parent / "config.json"

config_file.touch(exist_ok=True)

def load(key = "server"):
    default = copy.deepcopy(default_config)
    cfg = config_file.read_bytes()
    if len(cfg) > 0:
        default.update(orjson.loads(config_file.read_bytes()))
    return default.get(key, {})

def init(key="server"):
    app.storage.general["config"] = default_config.get(key)
    app.storage.general["config"].update(load(key))

def save(key="server"):
    config_json = {}
    config_bytes = config_file.read_bytes()
    if len(config_bytes) > 0:
        config_json = orjson.loads(config_file.read_bytes())
    config_json[key] = app.storage.general.get("config", {})
    config_file.write_bytes(orjson.dumps(config_json, option=orjson.OPT_INDENT_2))
