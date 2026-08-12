# SPDX-License-Identifier: LGPL-2.1-or-later
"""Probe Sketcher construction-mode icon swaps on live QActions.

Run:
  timeout 25s flatpak run org.freecad.FreeCAD /path/to/NeoRibbon/scripts/probe_construction_icons.py
"""

from __future__ import annotations

import os
import traceback

import FreeCAD as App
import FreeCADGui as Gui

OUT = os.path.join(os.path.dirname(__file__), "probe_construction_icons.out")
_lines: list[str] = []

GEOMETRY = (
    "Sketcher_CreateLine",
    "Sketcher_CreatePolyline",
    "Sketcher_CreateArc",
    "Sketcher_CreateCircle",
    "Sketcher_CreateRectangle",
    "Sketcher_CreatePoint",
    "Sketcher_CreateSlot",
    "Sketcher_CreateBSpline",
    "Sketcher_CreateEllipseByCenter",
    "Sketcher_CompCreateCircle",
    "Sketcher_CompCreateArc",
    "Sketcher_CompCreateRectangles",
    "Sketcher_ToggleConstruction",
)


def log(msg: str) -> None:
    _lines.append(msg)
    try:
        App.Console.PrintMessage(f"NeoRibbon probe: {msg}\n")
    except Exception:
        pass


def flush() -> None:
    with open(OUT, "w", encoding="utf-8") as handle:
        handle.write("\n".join(_lines) + "\n")


def finish() -> None:
    flush()
    os._exit(0)


def pix_hash(dump: str | None) -> str:
    if not dump:
        return ""
    marker = " hash="
    if marker in dump:
        return dump.split(marker, 1)[1].split()[0]
    return dump


def icon_dump(icon) -> str:
    if icon is None:
        return "None"
    try:
        if icon.isNull():
            return "null"
    except Exception:
        return f"unreadable:{type(icon).__name__}"
    parts: list[str] = []
    for attr in ("name", "cacheKey", "themeName"):
        fn = getattr(icon, attr, None)
        if callable(fn):
            try:
                parts.append(f"{attr}={fn()!r}")
            except Exception:
                pass
    try:
        sizes = icon.availableSizes()
        parts.append(f"sizes={[ (s.width(), s.height()) for s in sizes ]}")
    except Exception:
        pass
    try:
        pix = icon.pixmap(24, 24)
        if pix is not None and not pix.isNull():
            ck = pix.cacheKey() if hasattr(pix, "cacheKey") else None
            parts.append(f"pix24={pix.width()}x{pix.height()} ck={ck}")
            try:
                img = pix.toImage()
                parts.append(
                    f"img={img.width()}x{img.height()} "
                    f"fmt={img.format()} hash={img.cacheKey() if hasattr(img, 'cacheKey') else None}"
                )
            except Exception:
                pass
    except Exception as exc:
        parts.append(f"pixmap_err={exc}")
    return " ".join(parts) or f"empty:{type(icon).__name__}"


def dump_command(name: str, label: str = "") -> None:
    prefix = f"{label}{name}" if label else name
    cmd = Gui.Command.get(name)
    if cmd is None:
        log(f"{prefix}: NOT FOUND")
        return
    info = {}
    try:
        info = cmd.getInfo() or {}
    except Exception as esc:
        log(f"{prefix}: getInfo failed: {esc}")
    pixmap = (info.get("pixmap") or "").strip()
    gui_icon = None
    gui_icon_dump = "n/a"
    if pixmap:
        try:
            gui_icon = Gui.getIcon(pixmap)
            gui_icon_dump = icon_dump(gui_icon)
        except Exception as exc:
            gui_icon_dump = f"getIcon failed: {exc}"
    actions = []
    try:
        raw = cmd.getAction()
        actions = list(raw) if raw else []
    except Exception as exc:
        log(f"{prefix}: getAction failed: {exc}")
        return
    log(
        f"{prefix}: actions={len(actions)} pixmap={pixmap!r} "
        f"menuText={info.get('menuText')!r} guiIcon=[{gui_icon_dump}]"
    )
    for i, action in enumerate(actions):
        try:
            sigs = []
            for sig in ("changed", "iconChanged", "toggled", "triggered"):
                if hasattr(action, sig):
                    sigs.append(sig)
            log(
                f"  [{i}] text={action.text()!r} checkable={action.isCheckable()} "
                f"checked={action.isChecked()} enabled={action.isEnabled()} "
                f"type={type(action).__name__} signals={sigs} "
                f"icon=[{icon_dump(action.icon())}]"
            )
        except Exception as exc:
            log(f"  [{i}] inspect failed: {exc}")


def action0(name: str):
    cmd = Gui.Command.get(name)
    if cmd is None:
        return None
    try:
        actions = list(cmd.getAction() or [])
    except Exception:
        return None
    return actions[0] if actions else None


def enter_sketch() -> None:
    doc = App.newDocument("NeoRibbonProbeConstruction")
    body = doc.addObject("PartDesign::Body", "Body")
    sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
    body.addObject(sketch)
    doc.recompute()
    Gui.ActiveDocument = Gui.getDocument(doc.Name)
    Gui.activeView().setActiveObject("pdbody", body)
    Gui.ActiveDocument.setEdit(sketch.Name)
    log(f"created sketch {sketch.Name} in {doc.Name}")


def run():
    from PySide.QtCore import QTimer
    from PySide.QtWidgets import QToolButton, QToolBar

    def step1():
        try:
            Gui.activateWorkbench("PartDesignWorkbench")
            log("activated PartDesignWorkbench")
        except Exception as exc:
            log(f"activate PartDesignWorkbench failed: {exc}")
        QTimer.singleShot(600, step2)

    def step2():
        try:
            enter_sketch()
        except Exception:
            log("enter_sketch crashed:\n" + traceback.format_exc())
            finish()
            return
        QTimer.singleShot(800, step3)

    def step3():
        try:
            wb = Gui.activeWorkbench()
            log(f"workbench={type(wb).__name__} name={getattr(wb, 'name', lambda: '?')()}")
            try:
                items = wb.getToolbarItems() or {}
            except Exception as exc:
                log(f"getToolbarItems failed: {exc}")
                items = {}
            sketcher_cmds = []
            for toolbar, commands in items.items():
                hits = [str(c) for c in (commands or ()) if "Sketcher" in str(c)]
                if hits:
                    log(f"toolbar {toolbar!r}: {hits}")
                    sketcher_cmds.extend(hits)

            names = list(dict.fromkeys(list(GEOMETRY) + sketcher_cmds))
            log("--- BEFORE toggle ---")
            for name in names:
                dump_command(name)

            toggle = action0("Sketcher_ToggleConstruction")
            if toggle is None:
                log("no ToggleConstruction action; aborting")
                finish()
                return
            log(
                f"ToggleConstruction: checkable={toggle.isCheckable()} "
                f"checked={toggle.isChecked()} enabled={toggle.isEnabled()}"
            )

            before_icons = {}
            for name in GEOMETRY:
                act = action0(name)
                if act is None:
                    continue
                before_icons[name] = icon_dump(act.icon())

            mw = Gui.getMainWindow()
            ribbon_before = {}
            for obj_name in (
                "NeoRibbon_btn_Sketcher_CreateLine",
                "NeoRibbon_btn_Sketcher_CreatePolyline",
                "NeoRibbon_btn_Sketcher_CompCreateArc",
                "NeoRibbon_btn_Sketcher_CompCreateConic",
                "NeoRibbon_btn_Sketcher_ToggleConstruction",
            ):
                btn = mw.findChild(QToolButton, obj_name)
                ribbon_before[obj_name] = (
                    None if btn is None else icon_dump(btn.icon())
                )
            log("ribbon icons before:")
            for name, dump in ribbon_before.items():
                log(f"  {name}: {dump}")

            classic_btns = []
            for bar in mw.findChildren(QToolBar):
                for btn in bar.findChildren(QToolButton):
                    act = btn.defaultAction()
                    if act is None:
                        continue
                    text = (act.text() or "").replace("&", "")
                    if "Line" in text or "Circle" in text or "Construction" in text:
                        classic_btns.append(
                            f"tb={bar.objectName()!r}/{bar.windowTitle()!r} "
                            f"btn={btn.objectName()!r} text={text!r} "
                            f"icon=[{icon_dump(btn.icon())}] act=[{icon_dump(act.icon())}]"
                        )
            log(f"classic toolbar sample ({len(classic_btns)}):")
            for line in classic_btns[:20]:
                log("  " + line)

            changed_hits = []

            def on_changed(name, act):
                changed_hits.append(
                    f"changed {name} checkable={act.isCheckable()} "
                    f"checked={act.isChecked()} icon=[{icon_dump(act.icon())}]"
                )

            def on_icon_changed(name, act):
                changed_hits.append(
                    f"iconChanged {name} icon=[{icon_dump(act.icon())}]"
                )

            watched = []
            for name in GEOMETRY:
                act = action0(name)
                if act is None:
                    continue
                try:
                    act.changed.connect(lambda n=name, a=act: on_changed(n, a))
                    watched.append(name)
                except Exception as exc:
                    log(f"{name} changed.connect failed: {exc}")
                if hasattr(act, "iconChanged"):
                    try:
                        act.iconChanged.connect(
                            lambda _ic=None, n=name, a=act: on_icon_changed(n, a)
                        )
                    except Exception as exc:
                        log(f"{name} iconChanged.connect failed: {exc}")

            log(f"watching changed on: {watched}")

            try:
                Gui.runCommand("Sketcher_ToggleConstruction", 0)
                log("ran Gui.runCommand(Sketcher_ToggleConstruction, 0)")
            except Exception as exc:
                log(f"runCommand ToggleConstruction failed: {exc}")
                try:
                    toggle.trigger()
                    log("fell back to toggle.trigger()")
                except Exception as exc2:
                    log(f"toggle.trigger failed: {exc2}")

            QTimer.singleShot(
                400, lambda: step4(before_icons, changed_hits, ribbon_before)
            )
        except Exception:
            log("step3 crashed:\n" + traceback.format_exc())
            finish()

    def step4(before_icons, changed_hits, ribbon_before):
        try:
            log("--- AFTER toggle ---")
            for name in GEOMETRY:
                dump_command(name)
            log(f"changed/iconChanged hits ({len(changed_hits)}):")
            for line in changed_hits[:80]:
                log("  " + line)
            log("--- icon compare ---")
            for name, before in before_icons.items():
                act = action0(name)
                after = icon_dump(act.icon()) if act is not None else "gone"
                changed = before != after
                log(f"{name}: {'CHANGED' if changed else 'same'} before=[{before}] after=[{after}]")

            mw = Gui.getMainWindow()
            log("--- ribbon icon compare ---")
            for obj_name, before in ribbon_before.items():
                btn = mw.findChild(QToolButton, obj_name)
                if btn is None:
                    log(f"{obj_name}: not found")
                    continue
                after = icon_dump(btn.icon())
                act = action0(obj_name.replace("NeoRibbon_btn_", ""))
                act_dump = icon_dump(act.icon()) if act is not None else "no-action"
                matches = pix_hash(after) == pix_hash(act_dump) and pix_hash(after)
                swapped = pix_hash(before) != pix_hash(after)
                status = "PASS" if swapped and matches else (
                    "PASS_STATIC" if matches and not swapped else "FAIL"
                )
                log(
                    f"{obj_name}: {status} "
                    f"{'SWAPPED' if swapped else 'same'} "
                    f"{'MATCHES_ACTION' if matches else 'MISMATCH_ACTION'} "
                    f"before_h={pix_hash(before)} after_h={pix_hash(after)} "
                    f"action_h={pix_hash(act_dump)}"
                )
        except Exception:
            log("step4 crashed:\n" + traceback.format_exc())
        finish()

    QTimer.singleShot(800, step1)


try:
    run()
except Exception:
    log("run() crashed:\n" + traceback.format_exc())
    flush()
