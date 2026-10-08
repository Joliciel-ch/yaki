from datetime import datetime

import httpx2
from fastapi import Request, Response
from nicegui import Client, app, core, ui

from yaki import config, records
from yaki.ui import Dialog, chart, gauge, settings
from yaki.ui.settings import camera_setting

ui.add_css('''

.q-field__native {

}
.q-field__control {

  font-size: 20px;
  height: 52px;
}
.q-dialog__inner {
    height: 100dvh !important;
    transform: none !important;
}
''', shared=True)


ui.add_head_html('''
    <style type="text/tailwindcss">
        @layer overrides {
            .ok_bg {
                @apply bg-gradient-to-tr from-[#84eaaa] to-[#d2ffca]
            }
            .warning_bg {
                @apply bg-gradient-to-tr from-[#eeee80] to-[#fffeca]
            }
            .alert_bg {
                @apply bg-gradient-to-tr from-[#ff6f6f] to-[#ffcaca]
            }
            
        }
    </style>
    <meta name="mobile-web-app-capable" content="yes">
    <link rel="manifest" href="manifest.json" />
''', shared=True)

    
def setup() -> None:

    config.init()

    app.storage.general["region_points"] = {}

    @ui.page('/')
    async def index():

        help_dialog = Dialog()

        with help_dialog.overlay:
            with ui.card(align_items="start").classes("w-[500px] h-[500px] rounded-xl gap-2"):
                with ui.row(align_items="center").classes("w-full gap-1"):
                    ui.icon("help", size="lg", color="black")
                    ui.label("Aide").classes("text-xl text-black/90 font-semibold capitalize")
                    ui.space()
                    ui.button(icon="close", on_click=lambda: help_dialog.close(), color="black").props("outline round")
                ui.label("Pour toute question ou déclaration de bug: clem@joliciel.ch")
                ui.label("Module fréquentation")

        settings_dialog = settings.dialog()
        # ui.dark_mode(True)
        with ui.column(align_items="stretch").classes("w-full h-full gap-1"):
            with ui.row(align_items="center").classes("gap-0"):
                ui.space()
                ui.label(f"MAHN {datetime.now().strftime("%d/%m/%Y, %H:%M:%S")}").classes("text-xl font-bold")  # noqa: DTZ005
                ui.space()
                ui.button(icon='settings').props("round").classes("m-1").on("click", lambda: settings_dialog.open())
                ui.button(icon='help', on_click=lambda: help_dialog.open()).props("round").classes("m-1")
            
            with ui.row(align_items="stretch").classes("flex-grow w-full"):
                # card.set_visibility(False)

                with ui.card(align_items="center").tight().classes("flex-2 rounded-xl ok_bg transition duration-1000").mark('gauge_card'):
                    await gauge.render()

                with ui.card(align_items="center").tight().classes("rounded-xl flex-3 bg-gradient-to-b from-[#bcf4fe] to-[#ffffff]"):
                    await chart.render()



    @app.post('/record/{name}')
    def record(name: str, data: dict):
        # print(f"recevied data from {name}", data)
        app.storage.general["config"]["visitors"] = data.get("count", 0)
        records.server.create_record(data, name)
        # ui.notify(f"{name}: {data}")
    
    @app.post('/hello')
    def hello(data: dict):
        
        if "clients" not in app.storage.general["config"]:
            app.storage.general["config"]["clients"] = {}
        app.storage.general["config"]["clients"].update(
            { f"{data.get('host')}": dict(data) }
        )
        return {"hello there"}
        # ui.notify(f"{name}: {data}")
        
    @app.get("/generate_204")
    def gen204(request: Request):
        return Response(b'', 204)
    
    @app.get("/manifest.json")
    def manifest(request: Request):
        content = '''
{
  "short_name": "Yaki",
  "name": "Yaki People Counter",
    "start_url": "/",
    "scope": "/",
    "id": "/",
  "display": "fullscreen",
  "theme_color": "black",
  "background_color": "white"
}'''
        return Response(content.encode("utf-8"), media_type="application/manifest+json")
    
    @ui.page('/cameras')
    def cameras():
        with ui.row():
            ui.space()
            ui.button("back", on_click=lambda: ui.navigate.to("/")).props("round")

        for ip, client_data in app.storage.general["config"]["clients"].items():
            
            camera_setting(client_data)

            # def infos():
            #     app.storage.general["detect_results"] = str(httpx2.get(f'http://{host}/results').json())

            # ui.timer(interval=1, callback=infos)

    async def disconnect() -> None:
        """Disconnect all clients from current running server."""

        for client_id in Client.instances:
            await core.sio.disconnect(client_id)

    async def cleanup() -> None:
        config.save()
        await disconnect()

    app.on_shutdown(cleanup)
    # We also need to disconnect clients when the app is stopped with Ctrl+C,
    # because otherwise they will keep requesting images which lead to unfinished subprocesses blocking the shutdown.
    
    # def handle_sigint(signum, frame) -> None:
    #     # `disconnect` is async, so it must be called from the event loop; we use `ui.timer` to do so.
    #     ui.timer(0.1, disconnect, once=True)
    #     # Delay the default handler to allow the disconnect to complete.
    #     ui.timer(1, lambda: signal.default_int_handler(signum, frame), once=True)

    # signal.signal(signal.SIGINT, handle_sigint)

app.on_startup(setup)

def main():
    # All the setup is only done when the server starts. This avoids the webcam being accessed
    # by the auto-reload main process (see https://github.com/zauberzeug/nicegui/discussions/2321).
    
    ui.run(title="Yaki Server", host="0.0.0.0", port=8080, dark=False, reload=False, show=False)

# from multiprocessing import get_context
# import time
# import uvicorn
# from fastapi import FastAPI
# from nicegui import ui


# def run_gui():
#     app = FastAPI()
#     ui.run_with(app, title="Yaki Server", mount_path='/', dark=False)
#     uvicorn.run("yaki.server:main", host='0.0.0.0', port=8080, workers=1, reload=True, reload_includes=["./**/*.py"])

# def main_dev():
#     ctx = get_context('spawn')
#     gui_process = ctx.Process(target=run_gui)
#     gui_process.start()

#     time.sleep(2)
#     user_input = input('Confirm to stop the GUI process')

#     gui_process.terminate()
#     gui_process.join()

if __name__ in ["__main__", "__mp_main__"]:
    ui.run(title="Yaki Server", host="0.0.0.0", port=8080, dark=False)