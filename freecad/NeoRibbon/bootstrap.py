# SPDX-License-Identifier: LGPL-2.1-or-later
"""Wire NeoRibbon into the FreeCAD main window."""

from __future__ import annotations

import os
from typing import Optional

import FreeCAD as App
import FreeCADGui as Gui
from PySide.QtCore import QFileSystemWatcher, QTimer, Qt
from PySide.QtGui import QKeySequence, QShortcut
from PySide.QtWidgets import QApplication, QMainWindow, QMessageBox, QToolBar

from freecad.NeoRibbon import prefs
from freecad.NeoRibbon.commands import register as register_commands
from freecad.NeoRibbon.ribbon_bar import RibbonDock
from freecad.NeoRibbon.shortcut_conflicts import (
    find_shortcut_conflicts,
    normalize_shortcut,
)
from freecad.NeoRibbon.toolbar_ctrl import ToolbarController

_controller: Optional[ToolbarController] = None
_dock: Optional[RibbonDock] = None
_installed = False
_refresh_pending = False
_pref_observer = None
_pref_apply_pending = False
_escape_shortcuts: list = []
_fs_watcher: Optional[QFileSystemWatcher] = None
_quit_hooked = False
_AM_STOPFILE = "ADDON_DISABLED"

# Keys written by Edit → Preferences → NeoRibbon (and Tools dialog).
_PREF_PAGE_KEYS = frozenset(
    {
        "Enabled",
        "PromoteLarge",
        "ShowButtonLabels",
        "ButtonSize",
        "VisiblePerSection",
        "ChildCommandMode",
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
    return prefs.addon_root()


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
    """Re-apply last ribbon/classic mode after a workbench finishes loading."""
    global _refresh_pending
    if addon_disabled_by_manager():
        return
    if not prefs.last_mode_ribbon():
        # Classic last: let FreeCAD show this workbench's toolbars.
        return
    if _refresh_pending:
        return
    _refresh_pending = True

    def _do_refresh() -> None:
        global _refresh_pending
        _refresh_pending = False
        if addon_disabled_by_manager() or not prefs.last_mode_ribbon():
            return
        try:
            _show_ribbon()
        except Exception as exc:  # noqa: BLE001
            App.Console.PrintError(f"NeoRibbon: refresh failed: {exc}\n")

    # Single deferred shot so toolbar items exist; never poll in a loop.
    QTimer.singleShot(0, _do_refresh)


def _apply_last_mode() -> None:
    """Show ribbon or classic toolbars to match the last session."""
    global _refresh_pending
    if not _installed:
        return
    if addon_disabled_by_manager() or not prefs.last_mode_ribbon():
        _refresh_pending = False
        _hide_ribbon(restore_toolbars=True)
        return
    _show_ribbon()


def _on_about_to_quit() -> None:
    """Keep LastMode, and do not collapse a healthy classic layout on exit."""
    if _controller is None:
        return
    try:
        if prefs.last_mode_ribbon():
            # Ribbon was on: put classic bars back so Qt does not save empty chrome.
            _controller.restore_all_toolbars(touch_menubar=False, defer=False)
        else:
            # Classic was on: record what is visible; do not rebuild from snapshot.
            _controller.capture_visible_layout()
    except Exception:
        pass


def _ensure_quit_hook() -> None:
    global _quit_hooked
    if _quit_hooked:
        return
    try:
        app = QApplication.instance()
        if app is None:
            return
        app.aboutToQuit.connect(_on_about_to_quit)
        _quit_hooked = True
    except Exception:
        pass


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
        # Restore the user's saved classic toolbar layout.
        _controller.restore_all_toolbars()


def apply_prefs() -> None:
    """Re-apply preference values to the live UI (no FreeCAD restart needed)."""
    global _refresh_pending
    if not _installed:
        return
    prefs.sync_last_mode_from_enabled()
    _apply_last_mode()
    if prefs.last_mode_ribbon() and _dock is not None:
        _dock.refresh(force=True)
        if _controller is not None:
            _controller.show_menubar()


def toggle() -> None:
    prefs.set_enabled(not prefs.is_enabled())
    apply_prefs()
    state = "enabled" if prefs.is_enabled() else "disabled"
    App.Console.PrintMessage(f"NeoRibbon {state}\n")


def restore_toolbars() -> None:
    """Emergency recovery: re-dock classic toolbars + menu bar, ribbon off."""
    global _controller, _dock
    if _controller is None:
        _controller = ToolbarController()
    prefs.clear_legacy_hide_menubar()
    prefs.set_enabled(False)
    if _dock is not None:
        _dock.hide()
        try:
            _dock.setVisible(False)
        except Exception:
            pass
    # Re-dock bars that removeToolBar dropped out of View → Toolbars.
    _controller.recover_all_toolbars()


_SHORTCUT_SLOTS = {
    "toggle": toggle,
}


def _resolved_shortcut(kind: str, value: str | None = None) -> str:
    raw = prefs.shortcut(kind) if value is None else (value or "").strip()
    if not raw:
        raw = prefs.shortcut_default(kind)
    return normalize_shortcut(raw) or prefs.shortcut_default(kind)


def _clear_escape_shortcuts() -> None:
    """Drop NeoRibbon QShortcuts so they can be rebound from prefs."""
    global _escape_shortcuts
    mw = _main_window()
    victims = list(_escape_shortcuts)
    try:
        for sc in mw.findChildren(QShortcut):
            name = sc.objectName() or ""
            if name.startswith("NeoRibbon_shortcut_"):
                victims.append(sc)
    except Exception:
        pass
    seen: set[int] = set()
    for shortcut in victims:
        ident = id(shortcut)
        if ident in seen:
            continue
        seen.add(ident)
        try:
            shortcut.setEnabled(False)
            shortcut.setKey(QKeySequence())
            shortcut.setObjectName("")
            shortcut.setParent(None)
            shortcut.deleteLater()
        except Exception:
            pass
    _escape_shortcuts = []


def _bind_shortcut(kind: str, seq: str) -> bool:
    global _escape_shortcuts
    mw = _main_window()
    label = prefs.SHORTCUT_LABELS[kind]
    try:
        shortcut = QShortcut(QKeySequence(seq), mw)
        shortcut.setObjectName(prefs.SHORTCUT_OBJECT_NAMES[kind])
        shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        shortcut.setAutoRepeat(False)
        shortcut.activated.connect(_SHORTCUT_SLOTS[kind])
        _escape_shortcuts.append(shortcut)
        App.Console.PrintLog(f"NeoRibbon: shortcut {seq} → {label}\n")
        return True
    except Exception as exc:  # noqa: BLE001
        App.Console.PrintWarning(
            f"NeoRibbon: could not register {seq} ({label}): {exc}\n"
        )
        return False


def _shortcut_problems(desired: dict[str, str]) -> list[str]:
    """Uniqueness + foreign-binding problems for a proposed shortcut map."""
    problems: list[str] = []
    by_seq: dict[str, list[str]] = {}
    for kind, seq in desired.items():
        by_seq.setdefault(seq.casefold(), []).append(kind)
    for _seq_key, kinds in by_seq.items():
        if len(kinds) < 2:
            continue
        labels = ", ".join(prefs.SHORTCUT_LABELS[k] for k in kinds)
        problems.append(f"{desired[kinds[0]]} is assigned to more than one action ({labels})")

    mw = _main_window()
    for kind, seq in desired.items():
        try:
            conflicts = find_shortcut_conflicts(mw, seq)
        except Exception as exc:  # noqa: BLE001
            App.Console.PrintWarning(
                f"NeoRibbon: shortcut conflict scan failed ({exc}); "
                "continuing\n"
            )
            conflicts = []
        if conflicts:
            detail = "; ".join(conflicts[:8])
            if len(conflicts) > 8:
                detail += f"; …(+{len(conflicts) - 8} more)"
            label = prefs.SHORTCUT_LABELS[kind]
            problems.append(f"{label} ({seq}) conflicts with {detail}")
    return problems


def _warn_shortcut_problems(problems: list[str], *, interactive: bool) -> None:
    text = "; ".join(problems)
    if interactive:
        App.Console.PrintWarning(
            f"NeoRibbon: shortcut not applied: {text}. "
            "The previous NeoRibbon shortcuts were kept.\n"
        )
    else:
        App.Console.PrintWarning(
            f"NeoRibbon: shortcut conflict: {text}. "
            "Conflicting chords were skipped (Tools menu still works). "
            "Pick free keys under Tools → NeoRibbon preferences….\n"
        )
    if not interactive:
        return
    mw = _main_window()
    lines = "\n".join(f"• {p}" for p in problems[:12])
    if len(problems) > 12:
        lines += f"\n• …and {len(problems) - 12} more"
    try:
        QMessageBox.warning(
            mw,
            "NeoRibbon",
            (
                "Cannot apply keyboard shortcuts.\n\n"
                f"{lines}\n\n"
                "The previous NeoRibbon shortcuts were kept."
            ),
        )
    except Exception as exc:  # noqa: BLE001
        App.Console.PrintWarning(
            f"NeoRibbon: could not show shortcut conflict dialog: {exc}\n"
        )


def try_set_shortcuts(
    values: dict[str, str] | None = None,
    *,
    interactive: bool = False,
    persist: bool = True,
) -> bool:
    """Validate, optionally persist, and apply NeoRibbon shortcuts.

    Returns False on conflict when *interactive* (previous bindings kept).
    At startup, conflicting chords are skipped rather than stolen.
    """
    desired: dict[str, str] = {}
    for kind in prefs.SHORTCUT_KINDS:
        raw = None if values is None else values.get(kind)
        desired[kind] = _resolved_shortcut(kind, raw)

    problems = _shortcut_problems(desired)
    if problems and interactive:
        _warn_shortcut_problems(problems, interactive=True)
        return False

    skip: set[str] = set()
    if problems:
        _warn_shortcut_problems(problems, interactive=False)
        by_seq: dict[str, list[str]] = {}
        for kind, seq in desired.items():
            by_seq.setdefault(seq.casefold(), []).append(kind)
        for kinds in by_seq.values():
            if len(kinds) > 1:
                skip.update(kinds)
        mw = _main_window()
        for kind, seq in desired.items():
            if kind in skip:
                continue
            if find_shortcut_conflicts(mw, seq):
                skip.add(kind)

    if persist and not skip:
        for kind, seq in desired.items():
            prefs.set_shortcut(kind, seq)

    _clear_escape_shortcuts()
    for kind, seq in desired.items():
        if kind in skip:
            continue
        _bind_shortcut(kind, seq)
    return True


def reload_shortcuts(*, interactive: bool = False) -> bool:
    """Re-read shortcut prefs and apply them."""
    return try_set_shortcuts(interactive=interactive, persist=False)


def _register_escape_shortcuts() -> None:
    """
    Application-wide shortcuts for NeoRibbon commands.

    FreeCAD Accel on Tools menu actions can be unreliable; QShortcut with
    ApplicationShortcut stays available. Skip a binding when another command
    or widget already owns the sequence. The toggle chord comes from
    preferences (default: Ctrl+Shift+N).
    """
    try_set_shortcuts(interactive=False, persist=False)


def _resources_dir() -> str:
    return os.path.join(prefs.addon_root(), "Resources")


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
        from freecad.NeoRibbon.prefs_dialog import PreferencePage

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
    """Called once from freecad.NeoRibbon.init_gui."""
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
    prefs.clear_retired_shortcuts()
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
    _ensure_quit_hook()

    # Apply last session mode after FreeCAD restores window/toolbar state.
    # Shot 0: as soon as the event loop runs. Shot 400: after typical restoreState.
    if addon_disabled_by_manager():
        _hide_ribbon(restore_toolbars=True)
    else:
        mode = "ribbon" if prefs.last_mode_ribbon() else "classic"
        App.Console.PrintLog(f"NeoRibbon: starting in {mode} mode\n")
        QTimer.singleShot(0, _apply_last_mode)
        QTimer.singleShot(400, _apply_last_mode)

    App.Console.PrintLog("NeoRibbon installed\n")


def uninstall() -> None:
    """Restore classic UI and disconnect signals."""
    global _installed, _dock, _controller, _refresh_pending, _pref_observer
    global _escape_shortcuts, _fs_watcher, _quit_hooked
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
    if _quit_hooked:
        try:
            app = QApplication.instance()
            if app is not None:
                app.aboutToQuit.disconnect(_on_about_to_quit)
        except Exception:
            pass
        _quit_hooked = False
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
