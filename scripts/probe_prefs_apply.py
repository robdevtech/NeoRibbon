# SPDX-License-Identifier: LGPL-2.1-or-later
"""Probe Edit→Preferences Apply toggle + version label + observer GC.

Run:
  timeout 25s flatpak run org.freecad.FreeCAD /path/to/NeoRibbon/scripts/probe_prefs_apply.py
"""

from __future__ import annotations

import gc
import os
import traceback

import FreeCAD as App
import FreeCADGui as Gui

OUT = os.path.join(os.path.dirname(__file__), "probe_prefs_apply.out")
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


def pass_fail(name: str, ok: bool, detail: str = "") -> None:
    log(f"{'PASS' if ok else 'FAIL'} {name}" + (f" ({detail})" if detail else ""))


def snapshot(tag: str) -> dict:
    from PySide.QtWidgets import QDockWidget, QToolBar

    from freecad.NeoRibbon import bootstrap, prefs

    mw = Gui.getMainWindow()
    dock = mw.findChild(QDockWidget, "NeoRibbonDock")
    bars = [
        b
        for b in mw.findChildren(QToolBar)
        if not (b.objectName() or "").startswith("NeoRibbon")
    ]
    visible = [b.objectName() or "?" for b in bars if b.isVisible()]
    info = {
        "enabled": prefs.is_enabled(),
        "dock_vis": bool(dock is not None and dock.isVisible()),
        "visible_tb": len(visible),
        "contents": [],
    }
    try:
        info["contents"] = list(prefs.param_group().GetContents() or ())
    except Exception as exc:  # noqa: BLE001
        info["contents"] = [f"GetContents failed: {exc}"]
    log(
        f"{tag}: enabled={info['enabled']} dock={info['dock_vis']} "
        f"tb_vis={info['visible_tb']}"
    )
    for item in info["contents"]:
        if isinstance(item, (tuple, list)) and len(item) >= 2 and item[1] == "Enabled":
            log(f"  Enabled param={item!r}")
    return info


def run() -> None:
    from PySide.QtCore import QTimer

    def work() -> None:
        try:
            from freecad.NeoRibbon import bootstrap, prefs
            from freecad.NeoRibbon.prefs_dialog import PreferencePage, _version_label_text

            log(f"addon_version={prefs.addon_version()!r}")
            import freecad.NeoRibbon as nr

            log(f"freecad.NeoRibbon.__version__={nr.__version__!r}")
            log(f"version_label={_version_label_text()!r}")
            pass_fail(
                "package.xml version",
                prefs.addon_version() == "0.3.0",
                prefs.addon_version(),
            )

            wait_ms(500)
            start = snapshot("START")
            pass_fail(
                "startup ribbon",
                start["enabled"] and start["dock_vis"],
            )

            g1 = App.ParamGet(prefs.PARAM_PATH)
            g2 = App.ParamGet(prefs.PARAM_PATH)
            cached = prefs.param_group()
            log(f"ParamGet identity g1 is g2: {g1 is g2}")
            log(f"cached is g1: {cached is g1}")
            pass_fail(
                "cached param group is stable",
                cached is prefs.param_group(),
            )

            hits: list[str] = []

            class ProbeObs:
                def onChange(self, _group, name=None):
                    hits.append(str(name))

            # Temporary ParamGet.Attach must not survive GC (FreeCAD destructor).
            tmp_obs = ProbeObs()
            App.ParamGet(prefs.PARAM_PATH).Attach(tmp_obs)
            gc.collect()
            before = prefs.is_enabled()
            cached.SetBool("Enabled", not before)
            cached.SetBool("Enabled", before)
            wait_ms(50)
            temp_survived = "Enabled" in hits
            log(f"temp Attach hits after GC: {hits!r}")
            pass_fail(
                "temp ParamGet Attach dies on GC",
                not temp_survived,
                "observer still live" if temp_survived else "detached as expected",
            )

            # Cached group Attach must survive.
            hits.clear()
            live_obs = ProbeObs()
            cached.Attach(live_obs)
            gc.collect()
            cached.SetBool("Enabled", not before)
            cached.SetBool("Enabled", before)
            wait_ms(50)
            pass_fail(
                "cached ParamGet Attach survives GC",
                "Enabled" in hits,
                f"hits={hits!r}",
            )
            try:
                cached.Detach(live_obs)
            except Exception as exc:  # noqa: BLE001
                log(f"Detach probe obs: {exc}")

            # Observer-only disable (no explicit apply_prefs).
            prefs.set_enabled(False)
            wait_ms(250)
            off = snapshot("SETBOOL_OFF")
            pass_fail(
                "observer hides ribbon on SetBool(False)",
                (not off["enabled"]) and (not off["dock_vis"]) and off["visible_tb"] > 0,
                f"dock={off['dock_vis']} tb={off['visible_tb']}",
            )

            page = PreferencePage()
            page.loadSettings()
            ver = page.form.labelVersion.text()
            log(f"pref page version label={ver!r}")
            pass_fail(
                "pref page version label",
                prefs.addon_version() in ver and ver.startswith("NeoRibbon"),
                ver,
            )
            page.form.checkEnabled.setChecked(True)
            page.saveSettings()
            wait_ms(200)
            on_page = snapshot("PAGE_SAVE_ON")
            pass_fail(
                "PreferencePage.saveSettings enables ribbon",
                on_page["enabled"] and on_page["dock_vis"],
            )

            page.form.checkEnabled.setChecked(False)
            page.saveSettings()
            wait_ms(250)
            off_page = snapshot("PAGE_SAVE_OFF")
            pass_fail(
                "PreferencePage.saveSettings hides ribbon",
                (not off_page["enabled"])
                and (not off_page["dock_vis"])
                and off_page["visible_tb"] > 0,
                f"dock={off_page['dock_vis']} tb={off_page['visible_tb']}",
            )

            # Restore for a clean session if the window close is skipped.
            page.form.checkEnabled.setChecked(True)
            page.saveSettings()
            wait_ms(150)
            snapshot("RESTORED")
        except Exception:
            log(traceback.format_exc())
        finally:
            flush()
            QTimer.singleShot(150, Gui.getMainWindow().close)

    QTimer.singleShot(700, work)


run()
