
import asyncio
from pathlib import Path

import orjson
from nicegui import app, ui

from yaki import records

gauge_options = orjson.loads((Path(__file__).parent / "default_gauge.json").read_bytes())

def update_gauge(gauge, record = None, card=None):

    conf = app.storage.general.get("config", {})

    if not record:
        record = records.server.get_last_record()

    value = (record.get("visitors", 0) or 0) + (record.get("staff", 0) or 0) + (record.get("correction", 0) or 0)

    max = record.get("maximum", 100)
    min = record.get("staff", 0) / max

    gauge.options["series"][0]["max"] = max
    gauge.options["series"][0]["detail"]["formatter"] = '{v|{value}}{t|\nsur }{p|%0.0f}{t| max.}' % max  # noqa: UP031

    caution = conf.get("caution_%", 95) / 100
    alert = conf.get("alert_%", 90) / 100

    bg_style = "ok"
    value_color = font_color = "#42FF20"
    if value >= caution * max:
        value_color = font_color = "#FFE100"
        bg_style = "warning"
    if value >= alert * max or value < 0:
        value_color = "#FF4141"
        font_color = "#FF0000"
        bg_style = "alert"

    gauge.options["graphic"][1]["style"]["stroke"] = value_color
    gauge.options["series"][0]["detail"]["rich"]["v"]["color"] = font_color

    gauge_colors = [
        [ min, "#9D9D9D" ],
        [ caution, "#82FF8C" ],
        [ alert, "#232008" ],
        [ 1, "#FF7575" ]
    ]

    gauge.options["series"][0]["axisLine"]["lineStyle"]["color"] = gauge_colors
    gauge.options["series"][0]["data"][0]["value"] = value

    if card:
        card.classes(remove="ok_bg warning_bg alert_bg")
        card.classes(add=f"{bg_style}_bg")

    gauge.options["graphic"][0]["shape"]["r"] = 190 # outer circle radius
    gauge.options["graphic"][1]["shape"]["r"] = 100 # inner circle radius

    gauge.update()


def live_update_gauge(gauge):
    update_gauge(gauge, records.server.get_last_record())

async def render():
    conf = app.storage.general.get("config", {})

    with ui.card(align_items="center").tight().classes("flex-1 rounded-xl ok_bg transition duration-1000") as gauge_card:
        with ui.row(align_items="center").classes("gap-1 w-full bg-gradient-to-b from-black/40 to-transparent p-2 pb-6 -mb-3"):
            # ui.space()
            # with ui.row(wrap=False).classes("items-center"):
            # with ui.element("div"):
            ui.icon("speed", size="lg", color="white")
            ui.label("Fréquentation").classes("text-xl text-white/90 font-semibold capitalize")
            ui.space()

        with ui.row().classes("gap-0 w-full"):
            gauge = ui.echart(gauge_options, renderer="canvas").classes("w-full min-h-[400px] -mb-[6em]")
            
            repeat_tasks = {}

            async def change_correction(button_name, amount):
                # conf = app.storage.general.get("config", {})
                conf["correction"] = conf.get("correction", 0) + amount
                records.server.create_record()
                update_gauge(gauge)
                await asyncio.sleep(1)
                while button_name in repeat_tasks:
                    conf["correction"] = conf.get("correction", 0) + amount
                    records.server.create_record()
                    update_gauge(gauge)
                    await asyncio.sleep(0.2)

            def start_repeat(button_name, amount):
                if button_name not in repeat_tasks:
                    repeat_tasks[button_name] = asyncio.create_task(
                        change_correction(button_name, amount)
                    )

            def stop_repeat(button_name):
                task = repeat_tasks.pop(button_name, None)
                if task:
                    task.cancel()

            with ui.column(align_items="center").classes("w-full h-[90px]"):
                ui.label("Correction").classes("z-10 text-black text-bold rounded-full")
                with ui.row(wrap=False, align_items="start").classes("z-10  w-[210px] gap-0 -m-12"):
                    ui.button("-1", color="black").props("outline round dense size='xl'") \
                            .on("mousedown", lambda: start_repeat("down", -1)) \
                            .on("mouseup", lambda: stop_repeat("down")) \
                            .on("mouseleave", lambda: stop_repeat("down")) \
                            .on("touchstart", lambda: start_repeat("down", -1)) \
                            .on("touchend", lambda: stop_repeat("down")) \
                        
                    
                    ui.label("0").bind_text_from(conf, "correction", backward=lambda v: f"+{v}" if v > 0 else f"{v}"
                                            ).classes("text-3xl font-bold flex-1 text-center pt-9")
                    
                    ui.button("+1", color="white").props("outline round dense size='xl'") \
                            .on("mousedown", lambda: start_repeat("up", 1)) \
                            .on("mouseup", lambda: stop_repeat("up")) \
                            .on("mouseleave", lambda: stop_repeat("up"))\
                            .on("touchstart", lambda: start_repeat("up", 1)) \
                            .on("touchend", lambda: stop_repeat("up"))

                ui.space()

            def nicernumber(number: ui.number):
                with ui.row(align_items="center").classes("w-full gap-0 p-0 m-0") as r:
                    def plus():
                        number.value = (number.value or 0) + 1
                    def minus():
                        number.value = (number.value or 0) - 1
                    ui.button("-1", on_click=minus).props("outline round dense size='md'")
                    ui.button("+1", on_click=plus).props("outline round dense size='md'")
                number.move(r, 1)
                number.classes("flex-1")

    live_gauge = ui.timer(1, lambda: live_update_gauge(gauge), active=False)
    live_update_gauge(gauge)
    live_gauge.activate()
