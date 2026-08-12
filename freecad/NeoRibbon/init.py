# SPDX-License-Identifier: LGPL-2.1-or-later
"""FreeCAD entry point (console + GUI).

init_gui.py is the normal GUI installer. FreeCAD imports this module after
__init__.py. If the GUI is already up (rare), schedule install.

Addon Manager does not load a newly installed or re-enabled Mod until the next
FreeCAD restart — there is no AM reload hook we can use.
"""

from __future__ import annotations

import FreeCAD as App


def _schedule_gui_install() -> None:
    if not getattr(App, "GuiUp", False):
        return
    try:
        import FreeCADGui as Gui
        from PySide.QtCore import QTimer
    except Exception:
        return

    def _install() -> None:
        try:
            if Gui.getMainWindow() is None:
                return
            from freecad.NeoRibbon.bootstrap import addon_disabled_by_manager, install

            if addon_disabled_by_manager():
                return
            install()
        except Exception as exc:  # noqa: BLE001
            App.Console.PrintError(f"NeoRibbon delayed install failed: {exc}\n")

    QTimer.singleShot(0, _install)


try:
    _schedule_gui_install()
except Exception:
    pass
