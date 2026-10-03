
from nicegui import app, ui

from yaki import config
from yaki import records



def dialog():

    async def save_and_close():
        config.save()
        await dialog.close()

    with ui.dialog() as dialog, ui.card(align_items="start").classes("w-[500px] rounded-xl gap-2"):
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
                ui.number("Visitors", min=0, max=1000, value=0).bind_value(app.storage.general, ("config", "visitors"))
                ui.number("Manual Correction", min=-200, max=200, value=0, precision=0).bind_value(
                    app.storage.general, ("config", "correction"), forward=lambda x: int(x))
                
                ui.button("Update", on_click=lambda: records.server.create_record())
            
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