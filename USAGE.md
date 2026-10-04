# Yaki dashboard usage

## Open the dashboard

Browse to `http://<server-address>:8080/` from a device that can reach the
Yaki server. On the intended Pi hotspot, the address is
`http://10.42.0.1:8080/`. The dashboard is designed for use on the local
network.

The main page has two panels: **Fréquentation** (occupancy) and **Historique**
(history). The interface labels are currently in French.

## Occupancy panel

The gauge shows the estimated building occupancy:

```text
visitors + planned staff + manual correction
```

It also shows the configured maximum capacity. The panel changes color as the
configured warning and alert percentages are reached: green indicates normal
occupancy, yellow indicates the warning range, and red indicates the alert
range (or a negative count).

Use the **-1** and **+1** buttons under **Correction** to adjust the count
manually. Holding a button repeats the adjustment. Corrections are included in
the gauge and recorded history.

## History panel

The chart plots the same adjusted occupancy value over time. Select **Semaine**
(week), **Aujourd'hui** (today), or **Dernière heures** (last hour) to change
the visible time window. Use the refresh button to reload the chart.

The adjacent download-shaped button currently calls the same chart refresh
action; it does not export a file.

## Settings

Select the gear button to open settings:

- **Maximum capacity** sets the gauge maximum.
- **Warning threshold** and **Alert threshold** set the occupancy percentages
  at which the gauge changes color.
- **Collaborateurs présents par jour** configures the planned staff count for
  each weekday. Staff is added to the occupancy shown in the gauge and chart.
- **Options développeur** exposes a direct visitor count, a manual correction,
  and an **Update** action to record the entered values.

Close the settings dialog with its close button to save the configuration.
The help button opens a dialog with project contact information.

## Live camera

The `/live` page shows frames from camera clients that have registered with
the server, with a **Back** link to the dashboard. It is intended for checking
the detector's view. The camera client must be running and connected for this
page to show a live feed.

## IMX500 detector preview and snapshot

For a local Raspberry Pi camera preview, run the line-crossing detector with
the `--display` flag:

```sh
uv run python src/yaki/better_imx500_counter.py --display
```

This opens a Tkinter window showing the camera image, counting line, and
detected person boxes. Close the window or press Ctrl+C to stop. Install
`python3-tk` if Tkinter is unavailable. Pillow is needed for rendering and is
normally available with the Raspberry Pi camera packages.

To save one annotated JPEG after the detector receives its first inference
result, provide a path with `--save-frame`:

```sh
uv run python src/yaki/better_imx500_counter.py --save-frame snapshot.jpg
```

The preview and snapshot options are optional; without them the detector runs
headlessly and does not capture full image arrays.

### Supervision / ByteTrack implementation

The line-crossing detector uses `ByteTrackTracker` from the Roboflow
`trackers` package and Supervision's `LineZone`, while continuing to use the
IMX500 as the detector:

```sh
uv run python src/yaki/imx500_crossing.py
uv run python src/yaki/imx500_crossing.py --display
uv run python src/yaki/imx500_crossing.py --save-frame snapshot.jpg
```

It uses a 0.80 track-activation threshold and passes person detections down to
0.10 confidence to ByteTrack's low-confidence association stage.

## Data and limitations

The server stores count history in `server_records.jsonl` and camera history
in `camera_records.jsonl` in the project directory. Configuration is stored in
`config.json`. The dashboard does not provide an export function for the
history at present.

The Pi setup and detector-to-dashboard integration have known gaps in the
current checkout; see the deployment notes in [README.md](./README.md) before
using this as an operational occupancy system.
