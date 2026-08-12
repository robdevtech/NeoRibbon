# SPDX-License-Identifier: LGPL-2.1-or-later
"""Probe NeoRibbon toggle/disable restore (and AM stopfile).

Run:
  timeout 25s flatpak run org.freecad.FreeCAD /path/to/NeoRibbon/scripts/probe_toggle_restore.py
"""

from __future__ import annotations

import os
import traceback

import FreeCAD as App
import FreeCADGui as Gui

OUT = os.path.join(os.path.dirname(__file__), "probe_toggle_restore.out")
_lines: list[str] = []


def log(msg: str) -> None:
    _lines.append(msg)
    try:
        App.Console.PrintMessage(f"NeoRibbon probe: {msg}\n")
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


def snapshot(tag: str) -> dict:
    from PySide.QtWidgets import QDockWidget, QToolBar

    from freecad.NeoRibbon import bootstrap, prefs

    mw = Gui.getMainWindow()
    dock = mw.findChild(QDockWidget, "NeoRibbonDock")
    bars = [b for b in mw.findChildren(QToolBar) if not (b.objectName() or "").startswith("NeoRibbon")]
    visible = [b.objectName() or "?" for b in bars if b.isVisible()]
    hidden = [b.objectName() or "?" for b in bars if not b.isVisible()]
    menubar = mw.menuBar()
    ctrl = bootstrap._controller
    info = {
        "installed": bootstrap._installed,
        "enabled": prefs.is_enabled(),
        "am_disabled": bootstrap.addon_disabled_by_manager(),
        "dock": dock is not None,
        "dock_vis": bool(dock.isVisible()) if dock is not None else False,
        "visible_tb": len(visible),
        "hidden_tb": len(hidden),
        "menubar": bool(menubar is not None and menubar.isVisible()),
        "guard": bool(ctrl._enabled) if ctrl is not None else None,
    }
    log(
        f"{tag}: installed={info['installed']} enabled={info['enabled']} "
        f"am={info['am_disabled']} dock={info['dock']}/{info['dock_vis']} "
        f"tb_vis={info['visible_tb']} tb_hid={info['hidden_tb']} "
        f"menubar={info['menubar']} guard={info['guard']}"
    )
    log(f"  visible={visible[:24]}")
    log(f"  hidden={hidden[:24]}")
    return info


def pass_fail(name: str, ok: bool, detail: str = "") -> None:
    log(f"{'PASS' if ok else 'FAIL'} {name}" + (f" ({detail})" if detail else ""))


def run() -> None:
    from PySide.QtCore import QTimer

    def work() -> None:
        stop = None
        try:
            from freecad.NeoRibbon import bootstrap, prefs

            log("--- Addon Manager signals ---")
            try:
                import AddonManager as am

                inst = getattr(am, "INSTANCE", None)
                log(f"AddonManager.INSTANCE={inst}")
                if inst is not None:
                    sigs = [n for n in dir(inst) if "signal" in n.lower() or n in ("finished",)]
                    log(f"INSTANCE signal-ish: {sigs}")
                log(
                    "AM disable is ADDON_DISABLED stopfile + restart; "
                    "no global enable/disable signal"
                )
            except Exception as exc:  # noqa: BLE001
                log(f"AddonManager import: {exc}")

            wait_ms(400)
            before = snapshot("START")
            pass_fail(
                "startup ribbon",
                before["installed"] and before["enabled"] and before["dock_vis"],
            )

            bootstrap.toggle()
            off_now = snapshot("TOGGLE_OFF_immediate")
            wait_ms(500)
            off_later = snapshot("TOGGLE_OFF_500ms")
            pass_fail(
                "toggle-off immediate",
                (not off_now["enabled"])
                and (not off_now["dock_vis"])
                and off_now["visible_tb"] > 0
                and off_now["menubar"],
            )
            pass_fail(
                "toggle-off stays restored",
                (not off_later["enabled"])
                and (not off_later["dock_vis"])
                and off_later["visible_tb"] > 0
                and off_later["guard"] is False,
                f"vis={off_later['visible_tb']} hid={off_later['hidden_tb']}",
            )

            bootstrap.toggle()
            wait_ms(200)
            on_again = snapshot("TOGGLE_ON")
            pass_fail(
                "toggle-on immediate",
                on_again["enabled"] and on_again["dock_vis"],
            )

            prefs.set_enabled(False)
            bootstrap.apply_prefs()
            wait_ms(500)
            prefs_off = snapshot("PREFS_OFF_500ms")
            pass_fail(
                "prefs Enabled off",
                (not prefs_off["enabled"])
                and (not prefs_off["dock_vis"])
                and prefs_off["visible_tb"] > 0,
            )

            prefs.set_enabled(True)
            bootstrap.apply_prefs()
            wait_ms(200)
            prefs_on = snapshot("PREFS_ON")
            pass_fail("prefs Enabled on", prefs_on["enabled"] and prefs_on["dock_vis"])

            stop = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "ADDON_DISABLED",
            )
            with open(stop, "w", encoding="utf-8") as handle:
                handle.write("probe\n")
            wait_ms(400)
            am_off = snapshot("AM_STOPFILE")
            pass_fail(
                "AM stopfile restores UI",
                (not am_off["installed"] or not am_off["dock_vis"])
                and am_off["visible_tb"] > 0
                and am_off["menubar"],
                f"installed={am_off['installed']} vis={am_off['visible_tb']}",
            )
        except Exception:
            log(traceback.format_exc())
        finally:
            if stop and os.path.isfile(stop):
                try:
                    os.remove(stop)
                    log(f"removed stopfile {stop}")
                except Exception as exc:  # noqa: BLE001
                    log(f"FAILED to remove stopfile {stop}: {exc}")
            flush()
            QTimer.singleShot(150, Gui.getMainWindow().close)

    QTimer.singleShot(700, work)


run()
