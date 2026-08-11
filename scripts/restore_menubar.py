# SPDX-License-Identifier: LGPL-2.1-or-later
"""
Emergency recovery: show FreeCAD menu bar after NeoRibbon HideMenubar.

Run from a terminal (works when the menu bar is gone and you cannot open
the Python console):

  Flatpak:
    flatpak run org.freecad.FreeCAD /path/to/NeoRibbon/scripts/restore_menubar.py

  Native:
    freecad /path/to/NeoRibbon/scripts/restore_menubar.py

This script only clears HideMenubar and shows the menu bar. NeoRibbon stays
enabled unless you pass --restore-all on the command line / argv.
"""

from __future__ import annotations

import sys

import FreeCAD as App
import FreeCADGui as Gui

PARAM_PATH = "User parameter:BaseApp/Preferences/Mod/NeoRibbon"


def _want_restore_all() -> bool:
    return any(arg in ("--restore-all", "-a", "--disable") for arg in sys.argv)


def run() -> None:
    group = App.ParamGet(PARAM_PATH)
    group.SetBool("HideMenubar", False)
    if _want_restore_all():
        group.SetBool("Enabled", False)

    mw = Gui.getMainWindow()
    menubar = mw.menuBar() if mw is not None else None
    if menubar is not None:
        menubar.setVisible(True)
        menubar.show()

    try:
        from neoribbon import bootstrap

        if _want_restore_all():
            bootstrap.restore_toolbars()
        else:
            bootstrap.apply_prefs()
    except Exception as exc:  # noqa: BLE001
        App.Console.PrintWarning(
            f"NeoRibbon restore_menubar: apply_prefs skipped ({exc})\n"
        )

    if menubar is not None and menubar.isVisible():
        App.Console.PrintMessage(
            "NeoRibbon: menu bar restored (HideMenubar=False). "
            "Use Tools → NeoRibbon preferences or Ctrl+Shift+R if needed.\n"
        )
    else:
        App.Console.PrintError(
            "NeoRibbon: could not show menu bar — try quitting FreeCAD, then "
            "re-run this script, or set HideMenubar=0 in user.cfg.\n"
        )


run()
