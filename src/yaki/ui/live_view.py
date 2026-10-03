import httpx2
from nicegui import app, events, ui


def live_view(data):

    host = f"http://{data.get("host")}:{data.get("port")}"

    def mouse_handler(e: events.MouseEventArguments):
        i = app.storage.general["update_region_points"]
        app.storage.general["config"]["region_points"][i] = (int(e.image_x), int(e.image_y))
        app.storage.general["update_region_points"] = 1 if i == 0 else 0
        p = app.storage.general["config"]["region_points"]
        httpx2.get(f'{host}/region?{p[0][0]}&{p[0][1]}&{p[1][0]}&{p[1][1]}')

    with ui.card():
        with ui.row().classes("w-full"):
            ui.label(f"{data.get("name")} [{data.get("camera")}]").classes("text-xl")
            ui.space()
            ui.link("Back", "/")

        # with ui.row(align_items="center"):
            
        #     ui.switch('detect').bind_value(app.storage.general, "detect")
        #     ui.label().bind_text_from(app.storage.general, "detect_results")

        video_image = ui.interactive_image(f'{host}/frame', on_mouse=mouse_handler, events=['mousedown']) #.classes('max-w-[1280px]')

        ui.timer(interval=0.1, callback=video_image.force_reload)