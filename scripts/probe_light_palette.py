import FreeCADGui as Gui
from PySide.QtCore import QTimer
import sys
sys.path.insert(0, "/home/rob/projects/NeoRibbon")

def run():
    def dump():
        from neoribbon.theme import resolve_colors
        print("RESOLVED", resolve_colors())
        QTimer.singleShot(200, Gui.getMainWindow().close)
    QTimer.singleShot(400, dump)
run()
