
import copy
from pathlib import Path

from nicegui import app
import orjson

default_config = {
    "camera": {
        "host": "0.0.0.0",
        "port": 8081,
        "server_host": "127.0.0.1",
        "server_port": 8080,
        "type": "imx500",
        "name": "local",
        "imx500.enabled": True,
        "imx500.model": "/usr/share/imx500-models/imx500_network_yolo11n_pp.rpk",
        "imx500.line_pos": ((0, 0), (100, 100)),
        "imx500.invert_ins_outs": False,
        "imx500.track_timeout": 2,
        "imx500.track_threshold": 0.5,
        "imx500.confidence_threshold": 0.5,
        "imx500.min_consecutive_frames": 2,
        "imx500.detect_floor": 0.2,
        "imx500.fps": 12,
        "imx500.width": 1920,
        "imx500.height": 1080,
        "controls.AnalogueGain": 22.0,
        "controls.Brightness": 0,
        "controls.Contrast": 1,
        "controls.AeEnable": True,
        "controls.AeExposureMode": 1,
        "controls.AeMeteringMode": 2,
        "controls.ExposureValue": 0,
        #"controls.StatsOutputEnable": False,
        "controls.AeConstraintMode": 2,
        #"controls.AeExposureMode": 0,
        "controls.AnalogueGainMode": 1,
        #"controls.NoiseReductionMode": 1,
        #"controls.ExposureValue": 0,
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
        config_json = orjson.loads(config_file.read_bytes())
        default.update(config_json.get(key, {}))
        if key not in config_json:
            save(key, default)
    return default

def init(key="server"):
    app.storage.general["config"] = default_config.get(key)
    app.storage.general["config"].update(load(key))

def save(key="server", data=None):
    config_json = {}
    config_bytes = config_file.read_bytes()
    if len(config_bytes) > 0:
        config_json = orjson.loads(config_file.read_bytes())
    if key not in config_json:
        config_json[key] = {}
    if data:
        config_json[key].update(data)
    else:
        config_json[key] = app.storage.general.get("config", {})
    config_file.write_bytes(orjson.dumps(config_json, option=orjson.OPT_INDENT_2))
