import FreeCAD as App
import FreeCADGui as Gui
from PySide.QtCore import QTimer, Qt
from PySide.QtWidgets import QToolBar

WBS = ["BIMWorkbench", "SpreadsheetWorkbench", "CAMWorkbench", "PartDesignWorkbench"]

def dump(wb):
    mw = Gui.getMainWindow()
    print("===", wb, "===")
    for tb in mw.findChildren(QToolBar):
        name = tb.objectName() or "<empty>"
        area = mw.toolBarArea(tb)
        print(f"  vis={tb.isVisible()} area={int(area)} name={name!r} title={tb.windowTitle()!r}")

def run():
    seq = list(WBS)
    def step():
        if not seq:
            QTimer.singleShot(200, Gui.getMainWindow().close)
            return
        wb = seq.pop(0)
        try:
            Gui.activateWorkbench(wb)
        except Exception as e:
            print("fail", wb, e)
            QTimer.singleShot(300, step)
            return
        # dump immediately and after a short delay (late toolbars)
        QTimer.singleShot(0, lambda w=wb: dump(w + " t0"))
        QTimer.singleShot(300, lambda w=wb: (dump(w + " t300"), step()))
    QTimer.singleShot(400, step)

run()
