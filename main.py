from pathlib import Path
import signal
import subprocess
import httpx2

from nicegui import Client, app, core, events, run, ui

detect_addr = "http://127.0.0.1:8008"

def setup() -> None:

    app.storage.general["update_region_points"] = 0
    app.storage.general["region_points"] = [(0,0), (0,0)]

    @ui.page('/')
    def page():

        # if proc.poll() is not None:
        #     ui.notification(f"detector down ! ({proc.poll()})", color="red")

        def mouse_handler(e: events.MouseEventArguments):
            i = app.storage.general["update_region_points"]
            app.storage.general["region_points"][i] = (int(e.image_x), int(e.image_y))
            
            app.storage.general["update_region_points"] = 1 if i == 0 else 0

            p = app.storage.general["region_points"]

            httpx2.get(f'{detect_addr}/region?{p[0][0]}&{p[0][1]}&{p[1][0]}&{p[1][1]}')

        def infos():
            app.storage.general["detect_results"] = str(httpx2.get(f'{detect_addr}/results').json())

        with ui.row():
            ui.switch('detect').bind_value(app.storage.general, "detect")
            ui.label().bind_text_from(app.storage.general, "detect_results")
            ui.label().bind_text_from(app.storage.general, "region_points")

        video_image = ui.interactive_image(f'{detect_addr}/frame', on_mouse=mouse_handler, events=['mousedown']) #.classes('max-w-[1280px]')
        # A timer constantly updates the source of the image.
        ui.timer(interval=0.1, callback=video_image.force_reload)
        ui.timer(interval=1, callback=infos)

    async def disconnect() -> None:
        """Disconnect all clients from current running server."""
        for client_id in Client.instances:
            await core.sio.disconnect(client_id)

    def handle_sigint(signum, frame) -> None:
        # `disconnect` is async, so it must be called from the event loop; we use `ui.timer` to do so.
        ui.timer(0.1, disconnect, once=True)
        # Delay the default handler to allow the disconnect to complete.
        ui.timer(1, lambda: signal.default_int_handler(signum, frame), once=True)

    async def cleanup() -> None:
        # This prevents ugly stack traces when auto-reloading on code change,
        # because otherwise disconnected clients try to reconnect to the newly started server.

        await disconnect()
        # Release the webcam hardware so it can be used by other applications again.
        # vcap.release()

    app.on_shutdown(cleanup)
    # We also need to disconnect clients when the app is stopped with Ctrl+C,
    # because otherwise they will keep requesting images which lead to unfinished subprocesses blocking the shutdown.
    # signal.signal(signal.SIGINT, handle_sigint)


# All the setup is only done when the server starts. This avoids the webcam being accessed
# by the auto-reload main process (see https://github.com/zauberzeug/nicegui/discussions/2321).
app.on_startup(setup)

ui.run(workers=1)