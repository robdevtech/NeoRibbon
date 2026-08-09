# SPDX-License-Identifier: LGPL-2.1-or-later
"""Wire NeoRibbon into the FreeCAD main window."""

from __future__ import annotations

import os
from typing import Optional

import FreeCAD as App
import FreeCADGui as Gui
from PySide.QtCore import QTimer, Qt
from PySide.QtWidgets import QMainWindow, QToolBar

from neoribbon import prefs
from neoribbon.commands import register as register_commands
from neoribbon.ribbon_bar import RibbonDock
from neoribbon.toolbar_ctrl import ToolbarController

_controller: Optional[ToolbarController] = None
_dock: Optional[RibbonDock] = None
_installed = False
_refresh_pending = False
_pref_observer = None
_pref_apply_pending = False

# Keys written by Edit → Preferences → NeoRibbon (and Tools dialog).
_PREF_PAGE_KEYS = frozenset(
    {
        "Enabled",
        "HideMenubar",
        "PromoteLarge",
        "ShowButtonLabels",
        "ButtonSize",
        "VisiblePerSection",
        "IgnoredToolbars",
    }
)


class _PrefObserver:
    """Re-apply ribbon when FreeCAD preference Pref* widgets save."""

    def onChange(self, _group, name: str) -> None:
        if name not in _PREF_PAGE_KEYS:
            return
        _schedule_apply_prefs()


def _schedule_apply_prefs() -> None:
    global _pref_apply_pending
    if not _installed or _pref_apply_pending:
        return
    _pref_apply_pending = True

    def _run() -> None:
        global _pref_apply_pending
        _pref_apply_pending = False
        apply_prefs()

    QTimer.singleShot(0, _run)


def _main_window() -> QMainWindow:
    return Gui.getMainWindow()


def _on_workbench_activated(_name: str = "") -> None:
    """Refresh ribbon after FreeCAD finishes activating a workbench."""
    global _refresh_pending
    if not prefs.is_enabled() or _dock is None:
        return
    if _refresh_pending:
        return
    _refresh_pending = True

    def _do_refresh() -> None:
        global _refresh_pending
        _refresh_pending = False
        try:
            if _controller is not None:
                _controller.enable_guard()
                _controller.hide_classic_deferred()
                _controller.apply_menubar(prefs.hide_menubar())
            if _dock is not None:
                _dock.refresh()
        except Exception as exc:  # noqa: BLE001
            App.Console.PrintError(f"NeoRibbon: refresh failed: {exc}\n")

    # Single deferred shot so toolbar items exist; never poll in a loop.
    QTimer.singleShot(0, _do_refresh)


def _ensure_dock() -> RibbonDock:
    global _dock
    mw = _main_window()
    if _dock is not None:
        return _dock
    existing = mw.findChild(RibbonDock, "NeoRibbonDock")
    if existing is not None:
        _dock = existing
        return _dock
    _dock = RibbonDock(mw)
    mw.addDockWidget(Qt.DockWidgetArea.TopDockWidgetArea, _dock)
    return _dock


def _show_ribbon() -> None:
    global _controller
    dock = _ensure_dock()
    dock.show()
    if _controller is None:
        _controller = ToolbarController()
    _controller.enable_guard()
    _controller.hide_classic_deferred()
    _controller.apply_menubar(prefs.hide_menubar())
    dock.refresh()


def _hide_ribbon(restore_toolbars: bool = True) -> None:
    global _dock, _controller
    if _dock is not None:
        _dock.hide()
    if restore_toolbars and _controller is not None:
        _controller.restore()


def apply_prefs() -> None:
    """Re-apply preference values to the live UI (no FreeCAD restart needed)."""
    if not _installed:
        return
    if prefs.is_enabled():
        _show_ribbon()
        if _dock is not None:
            _dock.refresh(force=True)
        if _controller is not None:
            _controller.apply_menubar(prefs.hide_menubar())
    else:
        _hide_ribbon(restore_toolbars=True)


def toggle() -> None:
    prefs.set_enabled(not prefs.is_enabled())
    apply_prefs()
    state = "enabled" if prefs.is_enabled() else "disabled"
    App.Console.PrintMessage(f"NeoRibbon {state}\n")


def restore_toolbars() -> None:
    global _controller
    if _controller is None:
        _controller = ToolbarController()
    _controller.restore_all_toolbars()
    prefs.set_enabled(False)
    if _dock is not None:
        _dock.hide()


def _resources_dir() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "Resources",
    )


def _register_preference_page() -> None:
    resources = _resources_dir()
    icons = os.path.join(resources, "icons")
    ui = os.path.join(resources, "ui", "preferences.ui")
    if not os.path.isfile(ui):
        App.Console.PrintWarning(f"NeoRibbon: preference UI missing: {ui}\n")
        return

    # FreeCAD looks up "preferences-<group>" (lowercase) via icon paths.
    # Match Addon Manager: addIconPath only — do not Gui.addIcon(SVG bytes).
    try:
        if hasattr(Gui, "addIconPath") and os.path.isdir(icons):
            Gui.addIconPath(icons)
    except Exception as exc:  # noqa: BLE001
        App.Console.PrintWarning(
            f"NeoRibbon: preference icon path registration failed: {exc}\n"
        )

    try:
        Gui.addPreferencePage(ui, "NeoRibbon")
    except Exception as exc:  # noqa: BLE001
        App.Console.PrintWarning(f"NeoRibbon: addPreferencePage failed: {exc}\n")


def install() -> None:
    """Called once from InitGui.py."""
    global _installed, _controller, _pref_observer
    if _installed:
        return
    _installed = True

    register_commands()
    _register_preference_page()
    _controller = ToolbarController()

    _pref_observer = _PrefObserver()
    try:
        prefs.param_group().Attach(_pref_observer)
    except Exception as exc:  # noqa: BLE001
        App.Console.PrintWarning(
            f"NeoRibbon: preference observer failed: {exc}\n"
        )

    mw = _main_window()
    try:
        mw.workbenchActivated.connect(_on_workbench_activated)
    except Exception as exc:  # noqa: BLE001
        App.Console.PrintError(
            f"NeoRibbon: could not connect workbenchActivated: {exc}\n"
        )

    # Watch existing toolbars for late Show events (BIM/CAM/etc.).
    for toolbar in mw.findChildren(QToolBar):
        toolbar.installEventFilter(_controller)

    if prefs.is_enabled():
        # Defer first build until a real workbench is up.
        QTimer.singleShot(0, _show_ribbon)

    App.Console.PrintLog("NeoRibbon installed\n")


def uninstall() -> None:
    """Restore classic UI and disconnect signals."""
    global _installed, _dock, _controller, _refresh_pending, _pref_observer
    if not _installed:
        return
    mw = _main_window()
    try:
        mw.workbenchActivated.disconnect(_on_workbench_activated)
    except Exception:
        pass
    if _pref_observer is not None:
        try:
            prefs.param_group().Detach(_pref_observer)
        except Exception:
            pass
        _pref_observer = None
    _hide_ribbon(restore_toolbars=True)
    if _dock is not None:
        mw.removeDockWidget(_dock)
        _dock.deleteLater()
        _dock = None
    _controller = None
    _refresh_pending = False
    _installed = False
    App.Console.PrintLog("NeoRibbon uninstalled\n")
