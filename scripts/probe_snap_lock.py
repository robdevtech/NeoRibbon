# SPDX-License-Identifier: LGPL-2.1-or-later
"""Probe Draft Snap Lock vs Toggle Grid: QAction vs runCommand vs trigger.

Run:
  timeout 25s flatpak run org.freecad.FreeCAD /path/to/NeoRibbon/scripts/probe_snap_lock.py
"""

from __future__ import annotations

import os
import traceback

import FreeCAD as App
import FreeCADGui as Gui

OUT = os.path.join(os.path.dirname(__file__), "probe_snap_lock.out")
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


def dump_command(name: str) -> None:
    cmd = Gui.Command.get(name)
    if cmd is None:
        log(f"{name}: NOT FOUND")
        return
    info = {}
    try:
        info = cmd.getInfo() or {}
    except Exception as exc:  # noqa: BLE001
        log(f"{name}: getInfo failed: {exc}")
    shortcut = ""
    try:
        shortcut = str(cmd.getShortcut() or "")
    except Exception:
        shortcut = str(info.get("shortcut") or "")
    actions = []
    try:
        raw = cmd.getAction()
        actions = list(raw) if raw else []
    except Exception as exc:  # noqa: BLE001
        log(f"{name}: getAction failed: {exc}")
        return
    log(
        f"{name}: actions={len(actions)} shortcut={shortcut!r} "
        f"menuText={info.get('menuText')!r} pixmap={info.get('pixmap')!r}"
    )
    for i, action in enumerate(actions):
        try:
            log(
                f"  [{i}] text={action.text()!r} checkable={action.isCheckable()} "
                f"checked={action.isChecked()} enabled={action.isEnabled()} "
                f"type={type(action).__name__}"
            )
        except Exception as exc:  # noqa: BLE001
            log(f"  [{i}] inspect failed: {exc}")


def checked(name: str, index: int = 0):
    cmd = Gui.Command.get(name)
    if cmd is None:
        return None
    try:
        actions = list(cmd.getAction() or [])
    except Exception:
        return None
    if not (0 <= index < len(actions)):
        return None
    try:
        return bool(actions[index].isChecked())
    except Exception:
        return None


def action0(name: str):
    cmd = Gui.Command.get(name)
    if cmd is None:
        return None
    try:
        actions = list(cmd.getAction() or [])
    except Exception:
        return None
    return actions[0] if actions else None


def try_fn(label: str, name: str, fn) -> None:
    before = checked(name)
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        log(f"{name} {label}: ERROR {exc}")
        return
    after = checked(name)
    log(f"{name} {label}: checked {before} -> {after}")


def finish() -> None:
    flush()
    os._exit(0)


def run():
    from PySide.QtCore import QTimer
    from PySide.QtWidgets import QToolButton

    names_to_try = (
        "Draft_Snap_Lock",
        "Draft_ToggleGrid",
        "Draft_Snap",
        "Draft_ToggleSnap",
        "Draft_SnapLock",
    )

    def step1():
        try:
            Gui.activateWorkbench("DraftWorkbench")
            log("activated DraftWorkbench")
        except Exception as exc:  # noqa: BLE001
            log(f"activate DraftWorkbench failed: {exc}")
        QTimer.singleShot(700, step2)

    def step2():
        try:
            wb = Gui.activeWorkbench()
            log(f"workbench={type(wb).__name__}")
            for name in names_to_try:
                dump_command(name)

            try:
                items = wb.getToolbarItems() or {}
            except Exception as exc:  # noqa: BLE001
                log(f"getToolbarItems failed: {exc}")
                items = {}
            for toolbar, commands in items.items():
                for cname in commands or ():
                    low = str(cname).lower()
                    if "snap" not in low and "grid" not in low:
                        continue
                    dump_command(cname)

            snap = "Draft_Snap_Lock"
            grid = "Draft_ToggleGrid"
            snap_action = action0(snap)
            grid_action = action0(grid)
            if snap_action is None:
                log("no Snap Lock action; aborting toggles")
                finish()
                return

            try_fn("runCommand(0)", snap, lambda: Gui.runCommand(snap, 0))
            try_fn("runCommand()", snap, lambda: Gui.runCommand(snap))
            try_fn("action.trigger()", snap, snap_action.trigger)
            try_fn("action.toggle()", snap, snap_action.toggle)
            if grid_action is not None:
                try_fn("runCommand(0)", grid, lambda: Gui.runCommand(grid, 0))
                try_fn("action.trigger()", grid, grid_action.trigger)

            mw = Gui.getMainWindow()
            ribbon_btn = mw.findChild(QToolButton, "NeoRibbon_btn_Draft_Snap_Lock")
            grid_btn = mw.findChild(QToolButton, "NeoRibbon_btn_Draft_ToggleGrid")
            log(
                f"ribbon snap btn={ribbon_btn is not None} "
                f"checkable={getattr(ribbon_btn, 'isCheckable', lambda: None)()} "
                f"checked={getattr(ribbon_btn, 'isChecked', lambda: None)()}"
            )
            log(
                f"ribbon grid btn={grid_btn is not None} "
                f"checkable={getattr(grid_btn, 'isCheckable', lambda: None)()} "
                f"checked={getattr(grid_btn, 'isChecked', lambda: None)()}"
            )
            if ribbon_btn is not None:
                before_btn = ribbon_btn.isChecked()
                before_act = snap_action.isChecked()
                ribbon_btn.click()
                after_btn = ribbon_btn.isChecked()
                after_act = snap_action.isChecked()
                ok = after_act != before_act and after_btn == after_act
                log(
                    f"ribbon_btn.click(): btn {before_btn}->{after_btn} "
                    f"action {before_act}->{after_act} "
                    f"{'PASS' if ok else 'FAIL (click should toggle action+button)'}"
                )
            if grid_btn is not None and grid_action is not None:
                before_btn = grid_btn.isChecked()
                before_act = grid_action.isChecked()
                grid_btn.click()
                log(
                    f"grid_btn.click(): btn {before_btn}->{grid_btn.isChecked()} "
                    f"action {before_act}->{grid_action.isChecked()}"
                )
        except Exception:
            log("step2 crashed:\n" + traceback.format_exc())
        flush()
        os._exit(0)

    QTimer.singleShot(800, step1)


try:
    run()
except Exception:
    log("run() crashed:\n" + traceback.format_exc())
    flush()
