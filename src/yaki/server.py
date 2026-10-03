import httpx2
from fastapi import Request, Response
from nicegui import Client, app, core, ui

from yaki import config, records
from yaki.ui import chart, gauge, settings
from yaki.ui.live_view import live_view

ui.add_css('''

.q-field__native {

}
.q-field__control {

  font-size: 20px;
  height: 52px;
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
''', shared=True)

    
def setup() -> None:

    config.init()

    app.storage.general["update_region_points"] = 0
    app.storage.general["config"]["clients"] = {}

    @ui.page('/')
    async def index():

        with ui.dialog() as help_dialog, ui.card(align_items="start").classes("w-[500px] rounded-xl gap-2"):
            with ui.row(align_items="center").classes("w-full gap-1"):
                ui.icon("help", size="lg", color="black")
                ui.label("Aide").classes("text-xl text-black/90 font-semibold capitalize")
                ui.space()
                ui.button(icon="close", on_click=help_dialog.close, color="black").props("outline round")
            ui.label("Pour toute question ou déclaration de bug: clem@joliciel.ch")
            ui.label("Module fréquentation")

        # ui.dark_mode(True)
        with ui.row(align_items="stretch").classes("w-full h-full"):


            settings_dialog = settings.dialog()
            # card.set_visibility(False)

            await gauge.render()

            await chart.render()

            
        with ui.page_sticky(x_offset=18, y_offset=18).classes("gap-2"):
            ui.button(icon='settings', on_click=settings_dialog.open).props("round").classes("m-1")
            ui.button(icon='help', on_click=help_dialog.open).props("round").classes("m-1")


    @app.post('/record/{name}')
    def record(name: str, data: dict):
        # print(f"recevied data from {name}", data)
        app.storage.general["config"]["visitors"] = data.get("count", 0)
        records.server.create_record(data, name)
        # ui.notify(f"{name}: {data}")
    
    @app.post('/hello')
    def hello(data: dict, request: Request):
        
        if "clients" not in app.storage.general["config"]:
            app.storage.general["config"]["clients"] = {}
        app.storage.general["config"]["clients"].update(
            { f"{request.client.host}": dict(data) }
        )
        return {"hello there"}
        # ui.notify(f"{name}: {data}")
        
    @app.get("/generate_204")
    def gen204():
        return Response(b'', 204)
    
    @ui.page('/live')
    def live():
        for ip, data in app.storage.general["config"]["clients"].items():
            
            live_view(data)

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
    
    ui.run(title="Yaki Server", host="0.0.0.0", port=8080, workers=1, dark=False, reload=False)

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