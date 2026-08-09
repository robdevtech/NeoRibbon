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
        self._menubar_was_visible: bool | None = None
        self._filtering = False
        self._mw: QMainWindow | None = None

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
        mw = self._main_window()
        for toolbar in mw.findChildren(QToolBar):
            try:
                toolbar.installEventFilter(self)
            except Exception:
                pass
            self._track_and_hide(toolbar)

    def hide_classic_deferred(self) -> None:
        """Hide now and once more shortly after (late workbench toolbars)."""
        self.hide_classic()
        # Fixed dual-shot — not a poll loop. BIM/CAM often populate after t=0.
        QTimer.singleShot(0, self.hide_classic)
        QTimer.singleShot(150, self.hide_classic)
        QTimer.singleShot(400, self.hide_classic)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if not self._enabled or self._filtering:
            return False
        try:
            etype = event.type()
        except Exception:
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

    def apply_menubar(self, hide: bool) -> None:
        mw = self._main_window()
        menubar = mw.menuBar()
        if menubar is None:
            return
        if hide:
            if self._menubar_was_visible is None:
                self._menubar_was_visible = menubar.isVisible()
            menubar.hide()
        else:
            if self._menubar_was_visible is not None:
                menubar.setVisible(self._menubar_was_visible)
            else:
                menubar.show()
            self._menubar_was_visible = None

    def restore(self) -> None:
        self.disable_guard()
        mw = self._main_window()
        restored = 0
        for toolbar in mw.findChildren(QToolBar):
            name = toolbar.objectName() or ""
            if name in self._hidden_names or id(toolbar) in self._hidden_anon:
                toolbar.show()
                restored += 1
        self._hidden_names.clear()
        self._hidden_anon.clear()
        self.apply_menubar(False)
        App.Console.PrintLog(f"NeoRibbon: restored {restored} toolbars\n")

    def restore_all_toolbars(self) -> None:
        """Emergency recovery: show every non-NeoRibbon toolbar."""
        self.disable_guard()
        mw = self._main_window()
        for toolbar in mw.findChildren(QToolBar):
            name = toolbar.objectName() or ""
            if name.startswith("NeoRibbon"):
                continue
            toolbar.show()
        self._hidden_names.clear()
        self._hidden_anon.clear()
        menubar = mw.menuBar()
        if menubar is not None:
            menubar.show()
        self._menubar_was_visible = None
        App.Console.PrintMessage("NeoRibbon: all classic toolbars restored\n")
