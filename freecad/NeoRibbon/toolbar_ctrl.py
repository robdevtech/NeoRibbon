# SPDX-License-Identifier: LGPL-2.1-or-later
"""Hide and restore FreeCAD classic toolbars."""

from __future__ import annotations

import FreeCAD as App
import FreeCADGui as Gui
from PySide.QtCore import QEvent, QObject, QTimer, Qt
from PySide.QtWidgets import QMainWindow, QToolBar

_KEEP_VISIBLE_PREFIXES = ("NeoRibbon",)
_KEEP_VISIBLE_NAMES = frozenset({"StatusBar", "statusBar"})


class ToolbarController(QObject):
    """
    Track classic toolbars we hide so uninstall/disable can restore them.

    Some workbenches (BIM, CAM, Spreadsheet, …) create or re-show toolbars
    after activation, so we also guard Show/ChildAdded while the ribbon is on.
    """

    def __init__(self) -> None:
        super().__init__()
        self._enabled = False
        self._hidden_names: set[str] = set()
        self._hidden_anon: set[int] = set()
        self._filtering = False
        self._mw: QMainWindow | None = None
        self._hide_timers: list = []

    def _main_window(self) -> QMainWindow:
        return Gui.getMainWindow()

    def enable_guard(self) -> None:
        """Install event filter so late toolbars stay hidden."""
        self._enabled = True
        mw = self._main_window()
        if self._mw is not None and self._mw is not mw:
            try:
                self._mw.removeEventFilter(self)
            except Exception:
                pass
        self._mw = mw
        mw.installEventFilter(self)
        self.hide_classic()

    def disable_guard(self) -> None:
        self._enabled = False
        self._cancel_hide_timers()
        if self._mw is not None:
            try:
                self._mw.removeEventFilter(self)
            except Exception:
                pass
            self._mw = None

    def _should_skip(self, toolbar: QToolBar) -> bool:
        name = toolbar.objectName() or ""
        if name in _KEEP_VISIBLE_NAMES:
            return True
        if any(name.startswith(prefix) for prefix in _KEEP_VISIBLE_PREFIXES):
            return True
        # Keep true status-bar toolbars only; everything else is classic chrome.
        mw = self._main_window()
        try:
            area = mw.toolBarArea(toolbar)
        except Exception:
            return False
        if area == Qt.ToolBarArea.BottomToolBarArea and name.lower().startswith(
            "status"
        ):
            return True
        return False

    def _track_and_hide(self, toolbar: QToolBar) -> None:
        if self._should_skip(toolbar):
            return
        name = toolbar.objectName() or ""
        if name:
            self._hidden_names.add(name)
        else:
            self._hidden_anon.add(id(toolbar))
        if toolbar.isVisible():
            toolbar.hide()

    def hide_classic(self) -> None:
        if not self._enabled:
            return
        mw = self._main_window()
        if mw is None:
            return
        for toolbar in mw.findChildren(QToolBar):
            try:
                toolbar.installEventFilter(self)
            except Exception:
                pass
            self._track_and_hide(toolbar)

    def _cancel_hide_timers(self) -> None:
        for timer in self._hide_timers:
            try:
                timer.stop()
                timer.deleteLater()
            except Exception:
                pass
        self._hide_timers = []

    def hide_classic_deferred(self) -> None:
        """Hide now and once more shortly after (late workbench toolbars)."""
        self.hide_classic()
        # Fixed dual-shot — not a poll loop. BIM/CAM often populate after t=0.
        # Must be cancellable: otherwise a later shot re-hides after disable.
        self._cancel_hide_timers()
        for delay in (0, 150, 400):
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self.hide_classic)
            timer.start(delay)
            self._hide_timers.append(timer)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        try:
            etype = event.type()
        except Exception:
            return False

        # Restore before FreeCAD persists window state, so AM-disable + quit
        # cannot leave the next session with zero toolbars. Do not touch the
        # menu bar here — it is already being destroyed on close.
        if etype == QEvent.Type.Close and self._mw is not None and watched is self._mw:
            try:
                self._enabled = False
                self._cancel_hide_timers()
                self._show_classic_toolbars()
            except Exception:
                pass
            return False

        if not self._enabled or self._filtering:
            return False

        if etype == QEvent.Type.ChildAdded:
            try:
                child = event.child()
            except Exception:
                return False
            if isinstance(child, QToolBar):
                child.installEventFilter(self)
                QTimer.singleShot(0, self.hide_classic)
            return False

        if isinstance(watched, QToolBar):
            if etype in (QEvent.Type.Show, QEvent.Type.ShowToParent):
                if not self._should_skip(watched):
                    self._filtering = True
                    try:
                        self._track_and_hide(watched)
                    finally:
                        self._filtering = False
                    return True
            return False

        # Catch toolbars that were already children when the guard started.
        if etype == QEvent.Type.ChildPolished:
            try:
                child = event.child()
            except Exception:
                return False
            if isinstance(child, QToolBar):
                child.installEventFilter(self)
                QTimer.singleShot(0, self.hide_classic)

        return False

    def show_menubar(self) -> None:
        """Ensure the FreeCAD menu bar is visible (NeoRibbon never hides it)."""
        mw = self._main_window()
        if mw is None:
            return
        try:
            menubar = mw.menuBar()
        except Exception:
            return
        if menubar is None:
            return
        menubar.show()
        try:
            menubar.setVisible(True)
        except Exception:
            pass

    def _show_classic_toolbars(self) -> int:
        mw = self._main_window()
        if mw is None:
            return 0
        shown = 0
        for toolbar in mw.findChildren(QToolBar):
            name = toolbar.objectName() or ""
            if name.startswith("NeoRibbon"):
                continue
            try:
                toolbar.show()
                shown += 1
            except Exception:
                pass
        self._hidden_names.clear()
        self._hidden_anon.clear()
        return shown

    def restore(self) -> None:
        """Show toolbars we hid, then fall back to every classic toolbar."""
        self.disable_guard()
        self.restore_all_toolbars()

    def restore_all_toolbars(self, *, touch_menubar: bool = True) -> None:
        """Show every non-NeoRibbon toolbar (+ menu bar unless shutting down)."""
        self.disable_guard()
        shown = self._show_classic_toolbars()
        if touch_menubar:
            self.show_menubar()
        App.Console.PrintLog(f"NeoRibbon: restored {shown} classic toolbars\n")
