
import httpx2
from nicegui import app, events, ui

from yaki import config, records
from yaki.ui import Dialog


def dialog():

    dialog = Dialog()

    async def save_and_close():
        config.save()
        dialog.close()

    with dialog.overlay:
        with ui.card(align_items="start").classes("w-[500px] h-[500px] overflow-y-auto rounded-xl gap-2"):
            with ui.row(align_items="center").classes("w-full"):
                ui.icon("settings", size="lg", color="black")
                ui.label("Paramètres").classes("text-xl text-black/90 font-semibold capitalize")
                ui.space()
                ui.button(icon="close", on_click=save_and_close, color="black").props("outline round")

            with ui.row(align_items="baseline").classes("w-full"):
                ui.label("Capacité maximale du musée").classes("text-lg")
                ui.space()
                ui.number("Maximum Capacity", min=0, max=5000, value=200).bind_value(app.storage.general, ("config", "maximum"))

            ui.separator()

            with ui.row(align_items="baseline").classes("w-full"):
               ui.label("Seuil d'avertissement en pourcent").classes("text-lg")
               ui.space()
               ui.number("Caution thresold %", min=0, max=100, value=85).bind_value(app.storage.general, ("config", "caution_%"))

            ui.separator()

            with ui.row(align_items="baseline").classes("w-full"):    
                ui.label("Seuil d'alerte en pourcent").classes("text-lg")
                ui.space()
                ui.number("Alert thresold %", min=0, max=100, value=95).bind_value(app.storage.general, ("config", "alert_%"))

            ui.separator()

            with ui.expansion("Collaborateurs présents par jour").classes("text-lg w-full p-0 m-0"):

                with ui.row(align_items="baseline").classes("w-full"):
                    ui.space()
                    ui.label("Lundi")
                    ui.number("Monday Staff", min=0, max=5000, value=20).bind_value(app.storage.general, ("config", "staff_planning", "0"))
                        
                with ui.row(align_items="baseline").classes("w-full"):
                    ui.space()
                    ui.label("Mardi")
                    ui.number("Tuesday Staff", min=0, max=5000, value=20).bind_value(app.storage.general, 
                                                                                      ("config", "staff_planning", "1"))

                with ui.row(align_items="baseline").classes("w-full"):
                    ui.space()
                    ui.label("Mercredi")
                    ui.number("Tuesday Staff", min=0, max=5000, value=20).bind_value(app.storage.general, 
                                                                                 ("config", "staff_planning", "2"))
                
                with ui.row(align_items="baseline").classes("w-full"):
                    ui.space()
                    ui.label("Jeudi")
                    ui.number("Tuesday Staff", min=0, max=5000, value=20).bind_value(app.storage.general, 
                                                                                 ("config", "staff_planning", "3"))
                
                with ui.row(align_items="baseline").classes("w-full"):
                    ui.space()
                    ui.label("Vendredi")
                    ui.number("Tuesday Staff", min=0, max=5000, value=20).bind_value(app.storage.general, 
                                                                                 ("config", "staff_planning", "4"))
                
                with ui.row(align_items="baseline").classes("w-full"):
                    ui.space()
                    ui.label("Samedi")
                    ui.number("Tuesday Staff", min=0, max=5000, value=20).bind_value(app.storage.general, 
                                                                                 ("config", "staff_planning", "5"))     

                with ui.row(align_items="baseline").classes("w-full"):
                    ui.space()
                    ui.label("Dimanche")
                    ui.number("Tuesday Staff", min=0, max=5000, value=20).bind_value(app.storage.general, 
                                                                                     ("config", "staff_planning", "6"))

            ui.separator()

            with ui.expansion("Options dévelopeur").classes("text-lg w-full p-0 m-0"):
                with ui.row(align_items="baseline").classes("w-full"):
                    ui.number("Visitors", min=0, max=1000, value=0, precision=0).bind_value(app.storage.general, ("config", "visitors"))
                    ui.number("Manual Correction", min=-200, max=200, value=0, precision=0).bind_value(
                        app.storage.general, ("config", "correction"), forward=lambda x: int(x))

                    ui.button("Live View", on_click=lambda: ui.navigate.to("/cameras"))
                    ui.button("Update", on_click=lambda: records.server.create_record())

                    ui.button('rootCA', on_click=lambda: ui.download.file('/home/borel/yaki/root.crt'))
        # with ui.grid(columns=2).classes("text-white"):
        #     # ui.label("Settings").classes("text-xl")
        #     # ui.space()
        #     # ui.label("Current Count override")
        #     # ui.slider(min=0, max=200, value=100).bind_value(app.storage.general, ("config", "current_count"))
        #     ui.number("Visitors", min=0, max=1000, value=0).props("size='xl'").bind_value(app.storage.general, ("config", "visitors"))
        #     ui.number("Manual Correction", min=-200, max=200, value=0).props("size='xl'").bind_value(app.storage.general, ("config", "correction"))
        #     ui.number("Staff", min=0, max=5000, value=20).props("size='xl'").bind_value(app.storage.general, ("config", "staff"))
        #     ui.number("Caution thresold %", min=0, max=100, value=85).props("size='xl'").bind_value(app.storage.general, ("config", "caution_%"))
        #     ui.number("Alert thresold %", min=0, max=100, value=95).props("size='xl'").bind_value(app.storage.general, ("config", "alert_%"))
        #     ui.time_input("opening hour").props("size='xl'").bind_value(app.storage.general, ("config", "opening_time")).picker.props("format24h")
        #     ui.time_input("closing hour").props("size='xl'").bind_value(app.storage.general, ("config", "closing_time")).picker.props("format24h")

            
    return dialog


def camera_setting(data):

    host = f"http://{data.get("host")}:{data.get("port")}"

    if data.get("host") not in app.storage.general["region_points"]:
        app.storage.general["region_points"][data.get("host")] = {}

    store = app.storage.general["region_points"][data.get("host")] 
    
    store["current"] = 0
    store["points"] = httpx2.get(f'{host}/region').json()

    def mouse_handler(e: events.MouseEventArguments):
        i = store["current"]
        store["points"][i] = int(e.image_x)
        store["points"][i+1] = int(e.image_y)
        store["current"] = 2 if i == 0 else 0
        p = store["points"]
        httpx2.get(f'{host}/region?{p[0]}&{p[1]}&{p[2]}&{p[3]}')

    with ui.card().classes("w-full"):
        with ui.row().classes("w-full"):
            ui.label(f"Camera {data.get("name")} [{data.get("camera")}]").classes("text-xl")
            ui.space()
            ui.label(f"points {store}")

        # with ui.row(align_items="center"):

        #     ui.label().bind_text_from(app.storage.general, "detect_results")
        def on_change():
            httpx2.get(f'{host}/display')

        ui.switch("show live view", on_change=on_change)

        video_image = ui.interactive_image(f'{host}/frame', on_mouse=mouse_handler, events=['mousedown']) #.classes('max-w-[1280px]')

        ui.timer(interval=0.1, callback=video_image.force_reload)