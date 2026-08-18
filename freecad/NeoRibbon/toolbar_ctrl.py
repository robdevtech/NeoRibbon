# SPDX-License-Identifier: LGPL-2.1-or-later
"""Hide and restore FreeCAD classic toolbars."""

from __future__ import annotations

import FreeCAD as App
import FreeCADGui as Gui
from PySide.QtCore import QEvent, QObject, QSize, QTimer, Qt
from PySide.QtWidgets import QApplication, QMainWindow, QToolBar

from freecad.NeoRibbon import prefs

_KEEP_VISIBLE_PREFIXES = ("NeoRibbon",)
_KEEP_VISIBLE_NAMES = frozenset({"StatusBar", "statusBar"})
_AREA_TO_NAME = {
    Qt.ToolBarArea.TopToolBarArea: "top",
    Qt.ToolBarArea.BottomToolBarArea: "bottom",
    Qt.ToolBarArea.LeftToolBarArea: "left",
    Qt.ToolBarArea.RightToolBarArea: "right",
}
_NAME_TO_AREA = {name: area for area, name in _AREA_TO_NAME.items()}


class ToolbarController(QObject):
    """
    Track classic toolbars we hide so uninstall/disable can restore them.

    Some workbenches (BIM, CAM, Spreadsheet, …) create or re-show toolbars
    after activation, so we also guard Show/ChildAdded while the ribbon is on.

    Visibility, area, row breaks, and toolbar options are persisted
    (ToolbarSnapshot) so a later launch with the ribbon off can restore
    the user's layout — not the all-hidden Qt state from a session that
    ended with the ribbon on.
    """

    def __init__(self) -> None:
        super().__init__()
        self._enabled = False
        self._hidden_names: set[str] = set()
        self._hidden_anon: set[int] = set()
        self._user_hidden_names: set[str] = set()
        self._user_hidden_anon: set[int] = set()
        self._filtering = False
        self._mw: QMainWindow | None = None
        self._hide_timers: list = []
        self._restore_timers: list = []

    def _main_window(self) -> QMainWindow:
        return Gui.getMainWindow()

    def enable_guard(self) -> None:
        """Install event filter so late toolbars stay hidden."""
        self._cancel_restore_timers()
        self._enabled = True
        mw = self._main_window()
        if self._mw is not None and self._mw is not mw:
            try:
                self._mw.removeEventFilter(self)
            except Exception:
                pass
        self._mw = mw
        mw.installEventFilter(self)
        self._load_or_capture_snapshot()
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

    def _classic_toolbars(self) -> list[QToolBar]:
        mw = self._main_window()
        if mw is None:
            return []
        return [
            toolbar
            for toolbar in mw.findChildren(QToolBar)
            if not self._should_skip(toolbar)
        ]

    def _area_name(self, toolbar: QToolBar) -> str:
        try:
            if toolbar.isFloating():
                return "float"
        except Exception:
            pass
        mw = self._main_window()
        try:
            area = mw.toolBarArea(toolbar)
        except Exception:
            return "top"
        return _AREA_TO_NAME.get(area, "top")

    def _toolbar_options(self, toolbar: QToolBar) -> dict:
        opt: dict = {}
        try:
            size = toolbar.iconSize()
            opt["icon"] = [int(size.width()), int(size.height())]
        except Exception:
            pass
        try:
            opt["style"] = int(toolbar.toolButtonStyle())
        except Exception:
            pass
        try:
            opt["movable"] = bool(toolbar.isMovable())
        except Exception:
            pass
        try:
            opt["floatable"] = bool(toolbar.isFloatable())
        except Exception:
            pass
        return opt

    def _apply_toolbar_options(self, toolbar: QToolBar, opt: dict) -> None:
        if not opt:
            return
        icon = opt.get("icon")
        if isinstance(icon, (list, tuple)) and len(icon) == 2:
            try:
                toolbar.setIconSize(QSize(int(icon[0]), int(icon[1])))
            except Exception:
                pass
        if "style" in opt:
            try:
                toolbar.setToolButtonStyle(Qt.ToolButtonStyle(int(opt["style"])))
            except Exception:
                pass
        if "movable" in opt:
            try:
                toolbar.setMovable(bool(opt["movable"]))
            except Exception:
                pass
        if "floatable" in opt:
            try:
                toolbar.setFloatable(bool(opt["floatable"]))
            except Exception:
                pass

    def _split_into_rows(
        self, mw: QMainWindow, bars: list[QToolBar], *, horizontal: bool
    ) -> list[list[QToolBar]]:
        """Group toolbars into visual rows (or columns) using geometry + breaks."""
        if not bars:
            return []

        def _geo(toolbar: QToolBar):
            try:
                return toolbar.geometry()
            except Exception:
                return None

        if horizontal:
            bars = sorted(
                bars,
                key=lambda tb: (
                    (_geo(tb).y() if _geo(tb) else 0),
                    (_geo(tb).x() if _geo(tb) else 0),
                ),
            )
        else:
            bars = sorted(
                bars,
                key=lambda tb: (
                    (_geo(tb).x() if _geo(tb) else 0),
                    (_geo(tb).y() if _geo(tb) else 0),
                ),
            )
        rows: list[list[QToolBar]] = []
        current: list[QToolBar] = []
        for toolbar in bars:
            new_row = False
            if current:
                try:
                    if mw.toolBarBreak(toolbar):
                        new_row = True
                except Exception:
                    pass
                if not new_row:
                    prev = current[-1]
                    pg, cg = _geo(prev), _geo(toolbar)
                    if pg is not None and cg is not None:
                        if horizontal:
                            dy = abs(cg.y() - pg.y())
                            if dy > max(6, min(pg.height(), cg.height()) // 2):
                                new_row = True
                        else:
                            dx = abs(cg.x() - pg.x())
                            if dx > max(6, min(pg.width(), cg.width()) // 2):
                                new_row = True
            if new_row:
                rows.append(current)
                current = []
            current.append(toolbar)
        if current:
            rows.append(current)
        return rows

    def _as_rows(self, value) -> list[list[str]]:
        """Normalize snapshot order: list-of-rows, or legacy flat name list."""
        if not isinstance(value, list) or not value:
            return []
        if isinstance(value[0], list):
            rows: list[list[str]] = []
            for row in value:
                if not isinstance(row, list):
                    continue
                names = [str(name).strip() for name in row if str(name).strip()]
                if names:
                    rows.append(names)
            return rows
        return [[str(name).strip() for name in value if str(name).strip()]]

    def _layout_is_healthy(
        self,
        classic: list[QToolBar] | None = None,
        visible: list[QToolBar] | None = None,
    ) -> bool:
        """True when enough classic bars are showing to trust as the user layout."""
        if classic is None:
            classic = self._classic_toolbars()
        if visible is None:
            visible = [toolbar for toolbar in classic if toolbar.isVisible()]
        total = len(classic)
        showing = len(visible)
        # Need several bars on screen. One leftover bar is a hide-race or
        # Qt restoreState after a bad quit — never treat that as the user layout.
        # Also ignore early startup when FreeCAD has only created one toolbar.
        return total >= 3 and showing >= 3

    def _order_names(self, order) -> list[str]:
        names: list[str] = []
        if not isinstance(order, dict):
            return names
        for area_name in ("top", "bottom", "left", "right"):
            for row in self._as_rows(order.get(area_name)):
                names.extend(row)
        return names

    def _snapshot_is_corrupt(self, data: dict, classic: list[QToolBar] | None = None) -> bool:
        """True when a snapshot looks like a hide-race (one bar kept, rest marked hidden)."""
        if classic is None:
            classic = self._classic_toolbars()
        named = [toolbar.objectName() for toolbar in classic if toolbar.objectName()]
        order_names = self._order_names(data.get("order"))
        floats = data.get("float") if isinstance(data.get("float"), list) else []
        placed = len(order_names) + len(floats)
        hidden = data.get("hidden") if isinstance(data.get("hidden"), list) else []
        if len(named) >= 3 and placed <= 1:
            return True
        if len(hidden) >= 3 and placed <= 1:
            return True
        return False

    def _load_or_capture_snapshot(self) -> None:
        """Capture layout only when classic bars look complete; otherwise reuse prefs."""
        classic = self._classic_toolbars()
        visible = [toolbar for toolbar in classic if toolbar.isVisible()]
        if self._layout_is_healthy(classic, visible):
            self._capture_snapshot(classic)
            return
        data = prefs.toolbar_snapshot()
        hidden = data.get("hidden") if data else None
        if data and self._snapshot_is_corrupt(data, classic):
            self._user_hidden_names = set()
        elif isinstance(hidden, list):
            self._user_hidden_names = {
                str(name) for name in hidden if str(name).strip()
            }
        else:
            self._user_hidden_names = set()
        self._user_hidden_anon = set()

    def capture_visible_layout(self) -> None:
        """Persist the on-screen classic layout (classic-mode quit / healthy restore)."""
        classic = self._classic_toolbars()
        visible = [toolbar for toolbar in classic if toolbar.isVisible()]
        if self._layout_is_healthy(classic, visible):
            self._capture_snapshot(classic)

    def _capture_snapshot(self, classic: list[QToolBar]) -> None:
        mw = self._main_window()
        hidden: list[str] = []
        options: dict[str, dict] = {}
        floating: list[dict] = []
        by_area: dict[str, list[QToolBar]] = {
            "top": [],
            "bottom": [],
            "left": [],
            "right": [],
        }
        for toolbar in classic:
            name = toolbar.objectName() or ""
            if not name:
                if not toolbar.isVisible():
                    self._user_hidden_anon.add(id(toolbar))
                continue
            if not toolbar.isVisible():
                hidden.append(name)
                continue
            options[name] = self._toolbar_options(toolbar)
            try:
                if toolbar.isFloating():
                    geo = toolbar.geometry()
                    floating.append(
                        {
                            "name": name,
                            "x": int(geo.x()),
                            "y": int(geo.y()),
                            "w": int(geo.width()),
                            "h": int(geo.height()),
                        }
                    )
                    continue
            except Exception:
                pass
            area = self._area_name(toolbar)
            if area in by_area:
                by_area[area].append(toolbar)
        order: dict[str, list[list[str]]] = {}
        if mw is not None:
            order["top"] = [
                [tb.objectName() for tb in row]
                for row in self._split_into_rows(mw, by_area["top"], horizontal=True)
            ]
            order["bottom"] = [
                [tb.objectName() for tb in row]
                for row in self._split_into_rows(
                    mw, by_area["bottom"], horizontal=True
                )
            ]
            order["left"] = [
                [tb.objectName() for tb in row]
                for row in self._split_into_rows(mw, by_area["left"], horizontal=False)
            ]
            order["right"] = [
                [tb.objectName() for tb in row]
                for row in self._split_into_rows(
                    mw, by_area["right"], horizontal=False
                )
            ]
        row_count = sum(len(rows) for rows in order.values())
        visible_count = sum(len(row) for rows in order.values() for row in rows)
        prefs.set_toolbar_snapshot(
            {
                "hidden": hidden,
                "order": order,
                "options": options,
                "float": floating,
            }
        )
        self._user_hidden_names = set(hidden)
        App.Console.PrintLog(
            f"NeoRibbon: captured toolbar layout "
            f"({visible_count} visible in {row_count} row(s), "
            f"{len(hidden)} user-hidden, {len(floating)} floating)\n"
        )

    def _is_user_hidden(self, toolbar: QToolBar) -> bool:
        name = toolbar.objectName() or ""
        if name:
            return name in self._user_hidden_names
        return id(toolbar) in self._user_hidden_anon

    def _is_hidden_by_us(self, toolbar: QToolBar) -> bool:
        name = toolbar.objectName() or ""
        if name:
            return name in self._hidden_names
        return id(toolbar) in self._hidden_anon

    def _track_and_hide(self, toolbar: QToolBar) -> None:
        if self._should_skip(toolbar):
            return
        if self._is_user_hidden(toolbar):
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

    def _cancel_restore_timers(self) -> None:
        for timer in self._restore_timers:
            try:
                timer.stop()
                timer.deleteLater()
            except Exception:
                pass
        self._restore_timers = []

    def hide_classic_deferred(self) -> None:
        """Hide now and once more shortly after (late workbench toolbars)."""
        self.hide_classic()
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

        # Restore before FreeCAD persists window state, so the next session
        # is not saved with every classic toolbar hidden.
        if etype == QEvent.Type.Close and self._mw is not None and watched is self._mw:
            try:
                self._enabled = False
                self._cancel_hide_timers()
                self._restore_classic()
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

    def _is_undocked(self, toolbar: QToolBar) -> bool:
        """True after QMainWindow.removeToolBar: still a child, not in any area."""
        try:
            if toolbar.isFloating():
                return False
        except Exception:
            pass
        mw = self._main_window()
        if mw is None:
            return False
        try:
            return mw.toolBarArea(toolbar) == Qt.ToolBarArea.NoToolBarArea
        except Exception:
            return False

    def _undocked_classic(self) -> list[QToolBar]:
        return [
            toolbar for toolbar in self._classic_toolbars() if self._is_undocked(toolbar)
        ]

    def _restore_toggle_action(self, toolbar: QToolBar, *, checked: bool | None = None) -> None:
        """Put the bar back in View → Toolbars (removeToolBar drops that action)."""
        try:
            action = toolbar.toggleViewAction()
        except Exception:
            return
        if action is None:
            return
        try:
            action.setVisible(True)
        except Exception:
            pass
        if checked is not None:
            try:
                action.setChecked(bool(checked))
            except Exception:
                pass

    def _place_toolbar(self, toolbar: QToolBar, area) -> None:
        mw = self._main_window()
        if mw is None:
            return
        try:
            mw.addToolBar(area, toolbar)
        except Exception:
            pass

    def _redock_and_show(self, toolbar: QToolBar, area=None) -> bool:
        mw = self._main_window()
        if area is None:
            area = Qt.ToolBarArea.TopToolBarArea
            if mw is not None:
                try:
                    current = mw.toolBarArea(toolbar)
                    if current != Qt.ToolBarArea.NoToolBarArea:
                        area = current
                except Exception:
                    pass
        self._place_toolbar(toolbar, area)
        self._restore_toggle_action(toolbar, checked=True)
        try:
            toolbar.show()
            toolbar.setVisible(True)
            return True
        except Exception:
            return False

    def _reset_freecad_toolbar_prefs(self, names: list[str]) -> None:
        """Clear FreeCAD's saved hidden flags so setup() shows bars again."""
        try:
            group = App.ParamGet("User parameter:BaseApp/MainWindow/Toolbars")
        except Exception:
            return
        for name in names:
            if not name:
                continue
            try:
                group.RemBool(name)
            except Exception:
                try:
                    group.SetBool(name, True)
                except Exception:
                    pass
        try:
            saver = getattr(App, "saveParameter", None)
            if callable(saver):
                saver()
        except Exception:
            pass

    def _reactivate_workbench(self) -> None:
        """Ask FreeCAD to recreate workbench toolbars that were actually deleted."""
        try:
            workbench = Gui.activeWorkbench()
        except Exception:
            return
        try:
            name = workbench.name()
        except Exception:
            return
        if not isinstance(name, str) or not name.strip():
            return
        try:
            app = QApplication.instance()
            if app is not None and app.closingDown():
                return
        except Exception:
            pass
        try:
            Gui.activateWorkbench(name)
        except Exception:
            pass

    def _restore_area_rows(
        self, area_name: str, rows: list[list[str]], hidden: set[str], options: dict
    ) -> set[str]:
        mw = self._main_window()
        placed: set[str] = set()
        if mw is None:
            return placed
        area = _NAME_TO_AREA.get(area_name)
        if area is None:
            return placed
        first_row = True
        for row in rows:
            started = False
            for name in row:
                if name in hidden:
                    continue
                toolbar = mw.findChild(QToolBar, name)
                if toolbar is None or self._should_skip(toolbar):
                    continue
                if not first_row and not started:
                    try:
                        mw.addToolBarBreak(area)
                    except Exception:
                        pass
                self._place_toolbar(toolbar, area)
                self._apply_toolbar_options(toolbar, options.get(name) or {})
                self._restore_toggle_action(toolbar, checked=True)
                try:
                    toolbar.show()
                except Exception:
                    pass
                placed.add(name)
                started = True
            if started:
                first_row = False
        return placed

    def _restore_classic(self) -> int:
        """Restore user toolbar choices. Prefers the persisted snapshot."""
        mw = self._main_window()
        if mw is None:
            return 0
        if self._layout_is_healthy() and len(self._undocked_classic()) < 2:
            self.capture_visible_layout()
            shown = sum(1 for toolbar in self._classic_toolbars() if toolbar.isVisible())
            self._hidden_names.clear()
            self._hidden_anon.clear()
            return shown
        if len(self._undocked_classic()) >= 2:
            App.Console.PrintWarning(
                "NeoRibbon: classic toolbars were undocked from the main window; "
                "re-docking them so they appear under View → Toolbars\n"
            )
            shown = self._recover_all_classic()
            self._hidden_names.clear()
            self._hidden_anon.clear()
            return shown
        data = prefs.toolbar_snapshot()
        if data and not self._snapshot_is_corrupt(data):
            shown = self._restore_from_snapshot(data)
            expected = len(self._order_names(data.get("order")))
            if expected >= 3 and len(self._classic_toolbars()) < 3:
                shown = self._recover_all_classic()
        elif data and self._snapshot_is_corrupt(data):
            App.Console.PrintWarning(
                "NeoRibbon: toolbar snapshot looks incomplete "
                "(one bar kept); showing all classic toolbars\n"
            )
            shown = self._recover_all_classic()
        else:
            shown = self._restore_without_snapshot()
        self._hidden_names.clear()
        self._hidden_anon.clear()
        if len(self._undocked_classic()) >= 2:
            shown = self._recover_all_classic()
        elif shown and self._layout_is_healthy():
            self.capture_visible_layout()
        return shown

    def _restore_from_snapshot(self, data: dict) -> int:
        hidden = {
            str(name)
            for name in (data.get("hidden") or [])
            if str(name).strip()
        }
        self._user_hidden_names = set(hidden)
        options = data.get("options") or {}
        if not isinstance(options, dict):
            options = {}
        mw = self._main_window()
        placed: set[str] = set()
        order = data.get("order") or {}
        if isinstance(order, dict):
            for area_name in ("top", "bottom", "left", "right"):
                placed |= self._restore_area_rows(
                    area_name, self._as_rows(order.get(area_name)), hidden, options
                )
        floats = data.get("float") or []
        if isinstance(floats, list) and mw is not None:
            for item in floats:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                if not name or name in hidden or name in placed:
                    continue
                toolbar = mw.findChild(QToolBar, name)
                if toolbar is None or self._should_skip(toolbar):
                    continue
                self._place_toolbar(toolbar, Qt.ToolBarArea.TopToolBarArea)
                self._apply_toolbar_options(toolbar, options.get(name) or {})
                self._restore_toggle_action(toolbar, checked=True)
                try:
                    toolbar.show()
                    toolbar.move(int(item.get("x", 0)), int(item.get("y", 0)))
                    w, h = int(item.get("w", 0)), int(item.get("h", 0))
                    if w > 0 and h > 0:
                        toolbar.resize(w, h)
                except Exception:
                    pass
                placed.add(name)
        shown = len(placed)
        for toolbar in self._classic_toolbars():
            name = toolbar.objectName() or ""
            if name in hidden:
                try:
                    toolbar.hide()
                except Exception:
                    pass
                self._restore_toggle_action(toolbar, checked=False)
                continue
            if name and name in placed:
                continue
            if self._redock_and_show(toolbar):
                shown += 1
        return shown

    def _restore_without_snapshot(self) -> int:
        """Re-dock every classic bar except known user-hidden ones."""
        shown = 0
        have_session = bool(self._hidden_names or self._hidden_anon)
        for toolbar in self._classic_toolbars():
            if self._is_undocked(toolbar) and not self._is_user_hidden(toolbar):
                if self._redock_and_show(toolbar):
                    shown += 1
                continue
            if have_session and not self._is_hidden_by_us(toolbar):
                if self._is_user_hidden(toolbar):
                    try:
                        toolbar.hide()
                    except Exception:
                        pass
                    self._restore_toggle_action(toolbar, checked=False)
                continue
            if self._is_user_hidden(toolbar):
                try:
                    toolbar.hide()
                except Exception:
                    pass
                self._restore_toggle_action(toolbar, checked=False)
                continue
            if self._redock_and_show(toolbar):
                shown += 1
        return shown

    def _recover_all_classic(self) -> int:
        """Re-dock every remaining classic QToolBar and restore View → Toolbars."""
        prefs.clear_toolbar_snapshot()
        self._user_hidden_names.clear()
        self._user_hidden_anon.clear()
        classic = self._classic_toolbars()
        self._reset_freecad_toolbar_prefs(
            [toolbar.objectName() or "" for toolbar in classic]
        )
        shown = 0
        for toolbar in classic:
            if self._redock_and_show(toolbar):
                shown += 1
        self._reactivate_workbench()
        shown = sum(1 for toolbar in self._classic_toolbars() if toolbar.isVisible())
        if shown:
            self.capture_visible_layout()
        App.Console.PrintLog(
            f"NeoRibbon: recovered {shown} classic toolbars "
            "(re-docked + View → Toolbars actions restored)\n"
        )
        return shown

    def recover_all_toolbars(self, *, defer: bool = True) -> None:
        """Emergency restore: every leftover bar, ignoring a bad snapshot."""
        self.disable_guard()
        self._cancel_hide_timers()
        shown = self._recover_all_classic()
        self.show_menubar()
        if defer:
            self._cancel_restore_timers()
            for delay in (0, 200, 500):
                timer = QTimer(self)
                timer.setSingleShot(True)
                timer.timeout.connect(self._recover_all_classic)
                timer.start(delay)
                self._restore_timers.append(timer)
        App.Console.PrintMessage(
            f"NeoRibbon: restored {shown} classic toolbars "
            "(including bars missing from View → Toolbars)\n"
        )

    def restore(self) -> None:
        """Show classic toolbars using the saved user layout."""
        self.restore_all_toolbars()

    def restore_all_toolbars(
        self, *, touch_menubar: bool = True, defer: bool = True
    ) -> None:
        """Restore the user's classic toolbars. Does not un-hide user-hidden bars."""
        self.disable_guard()
        shown = self._restore_classic()
        if touch_menubar:
            self.show_menubar()
        if defer:
            self._schedule_restore_shots()
        else:
            self._cancel_restore_timers()
        App.Console.PrintLog(f"NeoRibbon: restored {shown} classic toolbars\n")

    def _schedule_restore_shots(self) -> None:
        """Re-apply restore after late workbench toolbars appear."""
        self._cancel_restore_timers()
        for delay in (0, 150, 400):
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._restore_classic)
            timer.start(delay)
            self._restore_timers.append(timer)
