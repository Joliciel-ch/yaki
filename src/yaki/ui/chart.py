from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from nicegui import app, run, ui
import orjson

from yaki import records

chart_options =  orjson.loads((Path(__file__).parent / "default_chart.json").read_bytes())

default_series_options = {
    #"sampling": "lttb",
    "name": 'Visitors',
    "type": 'line',
    "smooth": True,
    # "smoothMonotone": "x",
    "showSymbol": False,
    "showAllSymbol": False,
    # "symbolSize": 4,
    # "symbol": 'none',
    # "areaStyle": {},
    "data": [],
    "lineStyle": {
        "width": 4,
    },
}

def enable_chart_breaks(chart, enable=True):
    if not enable:
        chart.options["xAxis"]["breaks"] = []
        return

    year = 2026
    start = date(year, 1, 1)
    end = date(year + 1, 1, 1)
    opening = datetime.strptime(
        app.storage.general["config"].get("opening_time", "10:00"), "%H:%M").replace(tzinfo=UTC).time()
    closing = datetime.strptime(
        app.storage.general["config"].get("closing_time", "10:00"), "%H:%M").replace(tzinfo=UTC).time()

    breaks = [
        {
            "start": datetime.combine(day, closing),
            "end": datetime.combine(day + timedelta(days=1), opening),
            "gap": "1%",
        }
        for day in (start + timedelta(days=i) for i in range((end - start).days))
    ]

    chart.options["xAxis"]["breaks"] = breaks

async def update_chart(chart):
    chart.run_chart_method("showLoading")

    _records = await run.io_bound(records.server.get_all_records) or []

    _series = []

    # records = records[app.storage.client.get("_chart_index", 0):]

    conf = app.storage.general.get("config", {})

    serie = None
    for i, record in enumerate(_records, start=0):
        if not serie:
            serie = deepcopy(default_series_options)

        d = datetime.fromtimestamp(record.get("timestamp", 0), UTC).replace(microsecond=0)
        v = (record.get("visitors", 0) or 0) + (record.get("staff", 0) or 0) + (record.get("correction", 0) or 0)
        serie["data"] += [ [str(d), int(v or 0)] ]

        if i < len(_records)-1 and (_records[i+1].get("timestamp") - record.get("timestamp", 0)) > 3600:
            _series.append(serie)
            serie = None

    if serie:
        _series.append(serie)

    # app.storage.client["_chart_index"] = len(records)

    chart.options["series"] += _series

        # options["yAxis"]["max"] = max([ s[1] for s in series])
    # print("zoom", time.perf_counter() - t)



            # options["series"][0]["sampling"] = "average"
    # print(len(series))



    # chart.options["xAxis"]["min"] = datetime.now(timezone.utc) - timedelta(days=365)
    # chart.options["xAxis"]["max"] = datetime.now(timezone.utc) + timedelta(minutes=1)

    warning = conf.get("caution_%", 0) / 100 * conf.get("maximum", 1)
    alert = conf.get("alert_%", 0) / 100 * conf.get("maximum", 1)
    pieces = [
        {
            "lt": 0,
            "color": "#454545"
        },
        {
            "lte": conf.get("staff"),
            "color": "#9D9D9D"
        },
        {
            "gt": conf.get("staff"),
            "lte": warning,
            "color": "#3DEC1F"
        },
        {
            "gt": warning,
            "lte": alert,
            "color": "#EAC700"
        },
        {
            "gt": alert,
            "color": "#E70000"
        },
    ]

    chart.options["visualMap"]["pieces"] = pieces


    # for i, s in enumerate(_series):
    #     chart.run_chart_method("appendData", i, s)
    # if "startValue" in chart.options["dataZoom"][0]:
    #     del chart.options["dataZoom"][0]["startValue"]
    #     del chart.options["dataZoom"][0]["endValue"]
    chart.update()
    chart.run_chart_method("hideLoading")

async def render():
    with ui.card(align_items="center").tight().classes("rounded-xl flex-2 h-full bg-gradient-to-b from-[#bcf4fe] to-[#ffffff]"):
        async def update_chart_range(range = None):
            range = range or app.storage.client["chart_selected_zoom"]
            now = datetime.now(UTC)
            max = now + timedelta(minutes=1)
            # enable_chart_breaks(False)
            if range == "y":
                min = now - timedelta(days=365)
            elif range == "m":
                min = now - timedelta(days=31)
                # enable_chart_breaks(True)
            elif range == "w":
                min = now - timedelta(weeks=1)
                # enable_chart_breaks(True)
            elif range == "d":
                opening = datetime.strptime(
                                app.storage.general["config"].get("opening_time", "10:00"), "%H:%M").replace(tzinfo=UTC).time()
                min = now.replace(hour=opening.hour, minute=opening.minute)
            elif range == "h":
                min = now - timedelta(hours=1)

            chart.options["dataZoom"][0]["startValue"] = min
            chart.options["dataZoom"][0]["endValue"] = max
            
            # chart.options["xAxis"]["min"] = min
            # chart.options["xAxis"]["max"] = max
            chart.update()

        with ui.row(align_items="center").classes("gap-1 w-full bg-gradient-to-b from-black/40 to-transparent p-2 pb-6 -mb-1"):
            # ui.space()
            # with ui.row(wrap=False).classes("items-center"):
            # with ui.element("div"):
            ui.icon("bar_chart", size="lg", color="white")
            ui.label("Historique").classes("text-xl text-white/90 font-semibold capitalize")
            ui.space()
            ui.toggle({"w": "Semaine", "d": "Aujourd'hui", "h": "Dernière heures"}, 
                    value = "h").props("unelevated rounded size='md'").classes("bg-black/40 text-white ").on("click", update_chart_range).bind_value(app.storage.client, "chart_selected_zoom")
        
            ui.space()
            ui.button(icon="refresh", on_click=lambda: update_chart(chart), color="white").props("flat round dense")
            ui.button(icon="get_app", on_click=lambda: update_chart(chart), color="white").props("flat round dense")

        chart = ui.echart(chart_options).classes("p-2 w-full min-h-[300px]")
        app.storage.client["chart_selected_zoom"] = "h"

    await update_chart(chart)
    # live_chart = ui.timer(5, update_chart, active=False)
    await update_chart_range()

