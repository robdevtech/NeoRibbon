# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI smoke test for NeoRibbon. Run: FreeCAD NeoRibbon_smoke.py"""

from __future__ import annotations

import FreeCAD as App
import FreeCADGui as Gui


def run():
    from PySide.QtCore import QTimer
    from PySide.QtWidgets import QDockWidget

    def check():
        mw = Gui.getMainWindow()
        dock = mw.findChild(QDockWidget, "NeoRibbonDock")
        App.Console.PrintMessage(f"NeoRibbon smoke: dock={dock is not None}\n")
        from neoribbon import bootstrap

        App.Console.PrintMessage(
            f"NeoRibbon smoke: installed={bootstrap._installed}\n"
        )
        if dock is not None:
            App.Console.PrintMessage(
                f"NeoRibbon smoke: panels={dock.ribbon.panel_count}\n"
            )
        App.closeActiveTransaction() if hasattr(App, "closeActiveTransaction") else None
        QTimer.singleShot(100, Gui.getMainWindow().close)

    QTimer.singleShot(500, check)


run()
