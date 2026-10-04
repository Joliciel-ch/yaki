# Yaki

Yaki is an anonymous people-counting and occupancy-monitoring application for a
building. A camera and object detector count people entering and leaving; a
web dashboard shows the estimated current occupancy, configurable capacity
warnings, and recent history. The intended deployment runs both the detector
and dashboard on a Raspberry Pi, which can provide a Wi-Fi network for staff
to connect to.

## Architecture

The project has two main parts:

- **Detector / camera API** — `src/yaki/detect.py` uses Picamera2 and
  Ultralytics object counting, and serves a camera frame and count results on
  port `8081`. `src/yaki/camera.py` is another camera client (configured for a
  laptop webcam by default) that sends count records and camera registration
  to the dashboard.
- **Dashboard / server** — `src/yaki/server.py` is a NiceGUI web application
  listening on `0.0.0.0:8080`. It accepts count records, shows an occupancy
  gauge and history chart, and provides settings and a live-camera page.
- **Configuration and records** — `src/yaki/config.py` loads and saves
  `config.json`. `src/yaki/records.py` stores server and camera records as
  newline-delimited JSON in `server_records.jsonl` and `camera_records.jsonl`.

The intended data flow is camera detection → count records → dashboard gauge
and history. Camera images can be viewed on the local network at `/live`;
count history is recorded locally. The source currently contains separate
camera implementations, so see the deployment caveats below before relying on
the Pi setup script to connect them.

## Install and run

### Development

Requirements: Python 3.12 or newer and [uv](https://docs.astral.sh/uv/).

From the repository root:

```sh
uv sync
uv run yaki-server
```

Open [http://localhost:8080](http://localhost:8080). The server binds to all
network interfaces, so it can also be reached from another device on the same
network using the host machine's IP address.

The optional `yaki-camera` command starts `src/yaki/camera.py`, which expects
the configured camera source and a reachable Yaki server. The standalone
Picamera2 detector in `src/yaki/detect.py` requires Raspberry Pi camera
software and hardware in addition to the Python dependencies.

### Raspberry Pi setup

`setup.sh` is intended to configure NetworkManager, a Wi-Fi access point
(SSID `yaki`), local networking, and systemd services. It requires root and an
`AP_PASSWORD` environment variable; the intended invocation is:

```sh
sudo env AP_PASSWORD='choose-a-password' ./setup.sh
```

When configured, the dashboard is intended to be available at
`http://10.42.0.1:8080` from a device connected to the Pi's access point.

**The setup script is not currently turnkey in this checkout.** It refers to
`hotspot.iptables`, `src/main.py`, and `src/detect.py`, none of which exist at
those paths here. The application server is `src/yaki/server.py`, and the
detector is `src/yaki/detect.py`. The script also disables the detector
service. In addition, the standalone Picamera2 detector currently serves its
own API but does not post its counts to the dashboard. Resolve these paths and
connect the detector to the dashboard before using this as a Pi installation
procedure.

For dashboard controls and the meaning of its displayed values, see
[USAGE.md](./USAGE.md).
