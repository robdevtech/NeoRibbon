# SPDX-License-Identifier: LGPL-2.1-or-later
import FreeCAD as App
import FreeCADGui as Gui
from PySide.QtCore import QTimer


def run():
    def dump():
        try:
            Gui.activateWorkbench("PartDesignWorkbench")
        except Exception as exc:
            print("activate failed", exc)
        wb = Gui.activeWorkbench()
        print("WB", getattr(wb, "MenuText", wb))
        items = wb.getToolbarItems()
        for tb, cmds in items.items():
            print("TB", tb, "=>", list(cmds))
            for c in cmds:
                cl = str(c).lower()
                if "sketch" not in cl and "Sketch" not in str(c):
                    continue
                cmd = Gui.Command.get(c)
                info = cmd.getInfo() if cmd else {}
                print(" CMD", c, info)
                if cmd:
                    acts = cmd.getAction()
                    print("  actions", len(acts), [a.text() for a in acts[:10]])
        QTimer.singleShot(300, Gui.getMainWindow().close)

    QTimer.singleShot(600, dump)


run()
