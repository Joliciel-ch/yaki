

from nicegui import ui


class Dialog:

    def __init__(self):
        self.overlay = ui.column().style('''
            position: fixed;
            inset: 0;
            z-index: 99999;
            background: rgba(0,0,0,0.7);
            
            display: flex;
            align-items: center;
            justify-content: center;
        ''')
        self.close()

    def open(self):
        self.overlay.set_visibility(True)

    def close(self):
        self.overlay.set_visibility(False)