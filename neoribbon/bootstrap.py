# SPDX-License-Identifier: LGPL-2.1-or-later
"""Wire NeoRibbon into the FreeCAD main window."""

from __future__ import annotations

import os
from typing import Optional

import FreeCAD as App
import FreeCADGui as Gui
from PySide.QtCore import QFileSystemWatcher, QTimer, Qt
from PySide.QtGui import QKeySequence, QShortcut
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
_escape_shortcuts: list = []
_fs_watcher: Optional[QFileSystemWatcher] = None
_AM_STOPFILE = "ADDON_DISABLED"

# Keys written by Edit → Preferences → NeoRibbon (and Tools dialog).
_PREF_PAGE_KEYS = frozenset(
    {
        "Enabled",
        "PromoteLarge",
        "ShowButtonLabels",
        "ButtonSize",
        "VisiblePerSection",
        "IgnoredToolbars",
    }
)


class _PrefObserver:
    """Re-apply ribbon when FreeCAD preference Pref* widgets save."""

    def onChange(self, _group, name=None) -> None:
        key = "" if name is None else str(name)
        if key not in _PREF_PAGE_KEYS:
            return
        _schedule_apply_prefs()


def _schedule_apply_prefs() -> None:
    """Defer until the current Apply/OK batch finishes writing all Pref* keys."""
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


def _addon_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _am_stopfile() -> str:
    return os.path.join(_addon_dir(), _AM_STOPFILE)


def addon_disabled_by_manager() -> bool:
    """True when Addon Manager wrote ADDON_DISABLED (takes effect next restart)."""
    return os.path.isfile(_am_stopfile())


def _on_addon_dir_changed(_path: str = "") -> None:
    """AM disable/uninstall is a stopfile or deleted Mod dir — no Qt signal."""
    if not _installed:
        return
    gone = not os.path.isdir(_addon_dir())
    if gone or addon_disabled_by_manager():
        App.Console.PrintMessage(
            "NeoRibbon: Addon Manager disabled or removed this addon; "
            "restoring classic UI now (restart still required to unload)\n"
        )
        uninstall()


def _ensure_am_watcher() -> None:
    global _fs_watcher
    if _fs_watcher is not None:
        return
    root = _addon_dir()
    if not os.path.isdir(root):
        return
    watcher = QFileSystemWatcher()
    if not watcher.addPath(root):
        return
    watcher.directoryChanged.connect(_on_addon_dir_changed)
    _fs_watcher = watcher


def _on_workbench_activated(_name: str = "") -> None:
    """Refresh ribbon after FreeCAD finishes activating a workbench."""
    global _refresh_pending
    if not prefs.is_enabled() or addon_disabled_by_manager() or _dock is None:
        return
    if _refresh_pending:
        return
    _refresh_pending = True

    def _do_refresh() -> None:
        global _refresh_pending
        _refresh_pending = False
        if not prefs.is_enabled() or addon_disabled_by_manager() or _dock is None:
            return
        try:
            if _controller is not None:
                _controller.enable_guard()
                _controller.hide_classic_deferred()
                _controller.show_menubar()
            if _dock is not None and _dock.isVisible():
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
    if addon_disabled_by_manager():
        _hide_ribbon(restore_toolbars=True)
        return
    dock = _ensure_dock()
    dock.show()
    if _controller is None:
        _controller = ToolbarController()
    _controller.enable_guard()
    _controller.hide_classic_deferred()
    _controller.show_menubar()
    dock.refresh()


def _hide_ribbon(restore_toolbars: bool = True) -> None:
    global _dock, _controller
    if _dock is not None:
        _dock.hide()
        try:
            _dock.setVisible(False)
        except Exception:
            pass
    if restore_toolbars:
        if _controller is None:
            _controller = ToolbarController()
        # restore_all: do not rely on the hide-tracking set (timers / late bars).
        _controller.restore_all_toolbars()


def apply_prefs() -> None:
    """Re-apply preference values to the live UI (no FreeCAD restart needed)."""
    global _refresh_pending
    if not _installed:
        return
    if addon_disabled_by_manager() or not prefs.is_enabled():
        # Drop a queued workbench refresh so it cannot re-show after hide.
        _refresh_pending = False
        _hide_ribbon(restore_toolbars=True)
        return
    _show_ribbon()
    if _dock is not None:
        _dock.refresh(force=True)
    if _controller is not None:
        _controller.show_menubar()


def toggle() -> None:
    prefs.set_enabled(not prefs.is_enabled())
    apply_prefs()
    state = "enabled" if prefs.is_enabled() else "disabled"
    App.Console.PrintMessage(f"NeoRibbon {state}\n")


def restore_toolbars() -> None:
    """Emergency recovery: classic toolbars + menu bar, ribbon off."""
    global _controller
    if _controller is None:
        _controller = ToolbarController()
    prefs.clear_legacy_hide_menubar()
    prefs.set_enabled(False)
    _hide_ribbon(restore_toolbars=True)
    App.Console.PrintMessage(
        "NeoRibbon: restored classic UI (toolbars + menu bar); ribbon disabled\n"
    )


def _register_escape_shortcuts() -> None:
    """
    Application-wide shortcuts for NeoRibbon commands.

    FreeCAD Accel on Tools menu actions can be unreliable; QShortcut with
    ApplicationShortcut stays available.
    """
    global _escape_shortcuts
    if _escape_shortcuts:
        return
    mw = _main_window()
    bindings = (
        ("Ctrl+Shift+R", restore_toolbars, "NeoRibbon restore classic UI"),
        ("Ctrl+Shift+N", toggle, "NeoRibbon toggle"),
        (
            "Ctrl+Shift+,",
            lambda: __import__(
                "neoribbon.prefs_dialog", fromlist=["open_preferences_dialog"]
            ).open_preferences_dialog(),
            "NeoRibbon preferences",
        ),
    )
    for seq, slot, label in bindings:
        try:
            shortcut = QShortcut(QKeySequence(seq), mw)
            shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
            shortcut.activated.connect(slot)
            _escape_shortcuts.append(shortcut)
            App.Console.PrintLog(f"NeoRibbon: shortcut {seq} → {label}\n")
        except Exception as exc:  # noqa: BLE001
            App.Console.PrintWarning(
                f"NeoRibbon: could not register {seq}: {exc}\n"
            )


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
        from neoribbon.prefs_dialog import PreferencePage

        Gui.addPreferencePage(PreferencePage, "NeoRibbon")
    except Exception as exc:  # noqa: BLE001
        App.Console.PrintWarning(
            f"NeoRibbon: Python preference page failed ({exc}); "
            "falling back to UI file\n"
        )
        try:
            Gui.addPreferencePage(ui, "NeoRibbon")
        except Exception as fallback_exc:  # noqa: BLE001
            App.Console.PrintWarning(
                f"NeoRibbon: addPreferencePage failed: {fallback_exc}\n"
            )


def install() -> None:
    """Called once from InitGui.py."""
    global _installed, _controller, _pref_observer
    if _installed:
        return
    _installed = True

    register_commands()
    _register_preference_page()
    _register_escape_shortcuts()
    _controller = ToolbarController()

    # Older versions could hide the menu bar; clear that and always show it.
    prefs.clear_legacy_hide_menubar()
    _controller.show_menubar()

    _pref_observer = _PrefObserver()
    try:
        # Must keep this ParamGet wrapper; its destructor Detach()es observers.
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

    _ensure_am_watcher()

    if addon_disabled_by_manager() or not prefs.is_enabled():
        # Enabled-off or AM-disabled this session: never leave chrome empty.
        _hide_ribbon(restore_toolbars=True)
    else:
        # Defer first build until a real workbench is up.
        QTimer.singleShot(0, _show_ribbon)

    App.Console.PrintLog("NeoRibbon installed\n")


def uninstall() -> None:
    """Restore classic UI and disconnect signals."""
    global _installed, _dock, _controller, _refresh_pending, _pref_observer
    global _escape_shortcuts, _fs_watcher
    if not _installed:
        # Still restore if a previous session hid toolbars.
        _hide_ribbon(restore_toolbars=True)
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
    if _fs_watcher is not None:
        try:
            _fs_watcher.directoryChanged.disconnect(_on_addon_dir_changed)
        except Exception:
            pass
        try:
            _fs_watcher.deleteLater()
        except Exception:
            pass
        _fs_watcher = None
    for shortcut in _escape_shortcuts:
        try:
            shortcut.setParent(None)
            shortcut.deleteLater()
        except Exception:
            pass
    _escape_shortcuts = []
    _hide_ribbon(restore_toolbars=True)
    if _dock is not None:
        try:
            mw.removeDockWidget(_dock)
        except Exception:
            pass
        _dock.deleteLater()
        _dock = None
    _controller = None
    _refresh_pending = False
    _installed = False
    App.Console.PrintLog("NeoRibbon uninstalled\n")
