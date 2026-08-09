import FreeCAD as App
import FreeCADGui as Gui
from PySide.QtCore import QTimer
import sys
sys.path.insert(0, "/home/rob/projects/NeoRibbon")

def run():
    def dump():
        Gui.activateWorkbench("PartDesignWorkbench")
        from neoribbon.workbench_map import _command_meta, command_action_icon
        meta = _command_meta("PartDesign_CompSketches")
        icon = command_action_icon("PartDesign_CompSketches", 0)
        print("META", meta)
        print("ICON null?", icon is None or icon.isNull())
        QTimer.singleShot(200, Gui.getMainWindow().close)
    QTimer.singleShot(500, dump)
run()
