# SPDX-License-Identifier: LGPL-2.1-or-later
"""Probe NeoRibbon load after namespaced layout + content type other.

Run (script must be under the repo so Flatpak can read it):
  timeout 30s flatpak run org.freecad.FreeCAD /home/rob/projects/NeoRibbon/scripts/probe_load.py
"""

from __future__ import annotations

import os
import traceback

import FreeCAD as App
import FreeCADGui as Gui

OUT = os.path.join(os.path.dirname(__file__), "probe_load.out")
_lines: list[str] = []


def log(msg: str) -> None:
    _lines.append(msg)
    try:
        App.Console.PrintMessage(f"NeoRibbon probe_load: {msg}\n")
    except Exception:
        pass


def flush() -> None:
    with open(OUT, "w", encoding="utf-8") as handle:
        handle.write("\n".join(_lines) + "\n")


def wait_ms(ms: int) -> None:
    from PySide.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def run() -> None:
    from PySide.QtCore import QTimer
    from PySide.QtWidgets import QDockWidget

    def work() -> None:
        ok = True
        try:
            wait_ms(800)
            import freecad.NeoRibbon as nr
            from freecad.NeoRibbon import bootstrap, prefs

            log(f"import_ok=True module={nr.__name__!r} version={nr.__version__!r}")
            log(f"addon_root={prefs.addon_root()!r}")
            log(f"package_version={prefs.addon_version()!r}")
            log(f"installed={bootstrap._installed}")

            mw = Gui.getMainWindow()
            dock = mw.findChild(QDockWidget, "NeoRibbonDock") if mw else None
            log(f"dock={dock is not None}")
            if dock is not None and hasattr(dock, "ribbon"):
                log(f"panels={dock.ribbon.panel_count}")

            if prefs.addon_version() != "0.2.7":
                ok = False
                log("FAIL: unexpected package.xml version")
            if not bootstrap._installed:
                ok = False
                log("FAIL: bootstrap._installed is False")
            if dock is None:
                ok = False
                log("FAIL: NeoRibbonDock not found")

            log("RESULT=PASS" if ok else "RESULT=FAIL")
        except Exception:
            log("RESULT=FAIL")
            log(traceback.format_exc())
        finally:
            flush()
            QTimer.singleShot(100, Gui.getMainWindow().close)

    QTimer.singleShot(500, work)


run()
