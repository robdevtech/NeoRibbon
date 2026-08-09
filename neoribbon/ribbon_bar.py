# SPDX-License-Identifier: LGPL-2.1-or-later
"""Pure-Qt Office/Fusion-style ribbon bar (no third-party toolkit)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Optional

import FreeCAD as App
import FreeCADGui as Gui
from PySide.QtCore import QEvent, QPoint, QSize, Qt, QTimer
from PySide.QtGui import QFont, QIcon
from PySide.QtWidgets import (
    QAbstractItemView,
    QDockWidget,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from neoribbon import prefs, theme, usage
from neoribbon.workbench_map import (
    RibbonCommand,
    RibbonPanel,
    active_panels,
    active_workbench_name,
    command_action_icon,
    command_actions_meta,
    workbench_entries,
)


@dataclass(frozen=True)
class DensityStyle:
    """Visual metrics for small / medium / large ribbon density."""

    name: str
    ribbon_height: int
    content_height: int
    title_height: int
    rows: int
    small_icon: QSize
    large_icon: QSize
    small_btn_height: int
    small_btn_min_width: int
    large_btn_min_width: int
    small_show_text: bool
    label_chars: int


DENSITY_STYLES: dict[str, DensityStyle] = {
    "small": DensityStyle(
        name="small",
        ribbon_height=86,
        content_height=66,
        title_height=18,
        rows=3,
        small_icon=QSize(16, 16),
        large_icon=QSize(28, 28),
        small_btn_height=20,
        small_btn_min_width=22,
        large_btn_min_width=44,
        small_show_text=False,
        label_chars=10,
    ),
    "medium": DensityStyle(
        name="medium",
        ribbon_height=98,
        content_height=78,
        title_height=20,
        rows=3,
        small_icon=QSize(16, 16),
        large_icon=QSize(32, 32),
        small_btn_height=22,
        small_btn_min_width=72,
        large_btn_min_width=52,
        small_show_text=True,
        label_chars=11,
    ),
    "large": DensityStyle(
        name="large",
        ribbon_height=128,
        content_height=104,
        title_height=22,
        rows=2,
        small_icon=QSize(24, 24),
        large_icon=QSize(48, 48),
        small_btn_height=48,
        small_btn_min_width=100,
        large_btn_min_width=76,
        small_show_text=True,
        label_chars=14,
    ),
}

# Defaults used before a density is chosen (matches medium).
RIBBON_HEIGHT = DENSITY_STYLES["medium"].ribbon_height
LIST_ICON = QSize(18, 18)


def density_style(name: str | None = None) -> DensityStyle:
    key = (name or prefs.button_size()).lower()
    return DENSITY_STYLES.get(key, DENSITY_STYLES["medium"])


_ICON_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "Resources",
    "icons",
)


def _file_icon(name: str) -> QIcon:
    path = os.path.join(_ICON_DIR, name)
    return QIcon(path) if os.path.isfile(path) else QIcon()


def _icon_for(command: RibbonCommand, action_index: int = 0) -> QIcon:
    if command.pixmap:
        try:
            icon = Gui.getIcon(command.pixmap)
            if icon is not None and not icon.isNull():
                return icon
        except Exception as exc:  # noqa: BLE001
            App.Console.PrintWarning(
                f"NeoRibbon: getIcon({command.pixmap!r}) failed: {exc}\n"
            )
    # Compound commands often have an empty pixmap; use the action icon.
    action_icon = command_action_icon(command.name, action_index)
    if action_icon is not None:
        return action_icon
    return QIcon()


def _run_command(name: str, index: int = 0) -> None:
    if not name:
        return
    usage.record_use(name)
    try:
        Gui.runCommand(name, index)
    except TypeError:
        try:
            Gui.runCommand(name)
        except Exception as exc:  # noqa: BLE001
            App.Console.PrintError(f"NeoRibbon: runCommand({name!r}) failed: {exc}\n")
    except Exception as exc:  # noqa: BLE001
        App.Console.PrintError(
            f"NeoRibbon: runCommand({name!r}, {index}) failed: {exc}\n"
        )


def _short_label(text: str, limit: int = 14) -> str:
    cleaned = (text or "").replace("&", "").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 1)] + "…"


def _workbench_icon(icon_name: str) -> QIcon:
    if not icon_name:
        return QIcon()
    try:
        icon = Gui.getIcon(icon_name)
        if icon is not None and not icon.isNull():
            return icon
    except Exception:
        pass
    # Some workbenches store a filesystem path in Icon.
    if os.path.isfile(icon_name):
        return QIcon(icon_name)
    return QIcon()


def _activate_workbench(name: str) -> None:
    if not name:
        return
    try:
        Gui.activateWorkbench(name)
    except Exception as exc:  # noqa: BLE001
        App.Console.PrintError(f"NeoRibbon: activateWorkbench({name!r}) failed: {exc}\n")


def _help_page_for_command(command_name: str) -> str:
    """Best documentation page id for a FreeCAD command."""
    if not command_name:
        return ""
    try:
        command = Gui.Command.get(command_name)
        if command is not None:
            info = command.getInfo() or {}
            whats = str(info.get("whatsThis") or "").strip()
            # Skip known bad metadata (e.g. CompSketches → CompDatums).
            if whats and whats.replace(" ", "_") != "PartDesign_CompDatums":
                if command_name == "PartDesign_CompSketches":
                    return "Sketcher_NewSketch"
                if whats.replace(" ", "_") == command_name or whats.startswith(
                    command_name.split("_", 1)[0]
                ):
                    return whats
    except Exception:
        pass
    if command_name == "PartDesign_CompSketches":
        return "Sketcher_NewSketch"
    return command_name


def _open_command_help(command_name: str) -> None:
    """
    Open command docs quickly in the system browser.

    FreeCAD's Help.show() fetches and converts pages on the GUI thread, which
    feels slow. A direct wiki/browser open is effectively instant.
    """
    page = _help_page_for_command(command_name)
    if not page:
        return
    slug = page.replace(" ", "_")
    base = "https://wiki.freecad.org"
    try:
        help_prefs = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Help")
        custom = (help_prefs.GetString("URL", "") or "").rstrip("/")
        if custom:
            base = custom
    except Exception:
        pass
    url = f"{base}/{slug}"
    try:
        from PySide.QtCore import QUrl
        from PySide.QtGui import QDesktopServices

        if QDesktopServices.openUrl(QUrl(url)):
            return
    except Exception as exc:  # noqa: BLE001
        App.Console.PrintWarning(f"NeoRibbon: QDesktopServices open failed: {exc}\n")
    try:
        import webbrowser

        webbrowser.open(url, new=2)
    except Exception as exc:  # noqa: BLE001
        App.Console.PrintError(f"NeoRibbon: could not open help for {page!r}: {exc}\n")


def _help_icon() -> QIcon:
    for candidate in (":/icons/help-browser.svg", "help-browser", "help-browser.svg"):
        try:
            if candidate.startswith(":"):
                icon = QIcon(candidate)
            else:
                icon = Gui.getIcon(candidate)
            if icon is not None and not icon.isNull():
                return icon
        except Exception:
            continue
    return QIcon()


class WorkbenchSelector(QWidget):
    """Replaces FreeCAD's toolbar workbench combo while classic toolbars are hidden."""

    def __init__(
        self, style: DensityStyle, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._style = style
        self.setObjectName("NeoRibbon_workbench_selector")
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(style.ribbon_height)

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 2, 4, 0)
        root.setSpacing(0)

        self._button = QToolButton()
        self._button.setObjectName("NeoRibbon_workbench_button")
        self._button.setAutoRaise(True)
        self._button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self._button.setIconSize(style.large_icon)
        self._button.setFixedHeight(style.content_height - 4)
        self._button.setMinimumWidth(72 if style.name != "large" else 88)
        self._button.setToolTip("Switch workbench")
        root.addWidget(self._button)

        footer = QWidget()
        footer.setObjectName("NeoRibbon_group_footer")
        footer.setFixedHeight(style.title_height)
        foot = QHBoxLayout(footer)
        foot.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Workbench")
        title.setObjectName("NeoRibbon_group_title")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        title.setFont(QFont(QToolButton().font()))
        foot.addWidget(title)
        root.addWidget(footer)

        self._rebuild()

    def _rebuild(self) -> None:
        menu = QMenu(self._button)
        theme.apply_menu_theme(menu)
        current = active_workbench_name()
        current_title = "Workbench"
        current_icon = QIcon()

        for wb_name, title, icon_name in workbench_entries():
            icon = _workbench_icon(icon_name)
            action = menu.addAction(icon, title)
            action.setCheckable(True)
            action.setChecked(wb_name == current)
            if wb_name == current:
                current_title = title
                current_icon = icon
            action.triggered.connect(
                lambda _checked=False, n=wb_name: _activate_workbench(n)
            )

        if menu.isEmpty():
            empty = menu.addAction("No workbenches")
            empty.setEnabled(False)

        self._button.setMenu(menu)
        self._button.setIcon(current_icon)
        self._button.setText(_short_label(current_title, 12))
        theme.apply_chrome_palette(self._button)


class SectionListPopup(QFrame):
    """Popup list of every command in a section, with pin toggles."""

    def __init__(
        self,
        section: str,
        commands: list[RibbonCommand],
        on_changed: Optional[Callable[[], None]] = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName("NeoRibbon_section_list")
        self._section = section
        self._on_changed = on_changed
        self._pins_dirty = False

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(2)

        header = QLabel(f"{section} — all commands")
        font = QFont(header.font())
        font.setBold(True)
        header.setFont(font)
        root.addWidget(header)

        hint = QLabel(
            "Click a command to run it. Pin keeps it in the focus strip. "
            "? opens the wiki help page in your browser."
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        self._list = QListWidget()
        self._list.setObjectName("NeoRibbon_section_list_view")
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setMinimumWidth(320)
        self._list.setMaximumHeight(320)
        root.addWidget(self._list)

        self._pin_outline, self._pin_filled = theme.pin_icons()
        self._help_icon = _help_icon()
        theme.apply_widget_theme(self)

        pin_order = prefs.pinned_commands(section)
        pin_set = set(pin_order)
        original_index = {
            cmd.name: index
            for index, cmd in enumerate(commands)
            if getattr(cmd, "name", "")
        }
        ordered = usage.named_commands(commands)
        ordered.sort(
            key=lambda cmd: (
                0 if cmd.name in pin_set else 1,
                pin_order.index(cmd.name) if cmd.name in pin_set else 10_000,
                original_index.get(cmd.name, 10_000),
            )
        )

        for command in ordered:
            item = QListWidgetItem()
            item.setSizeHint(QSize(300, 28))
            self._list.addItem(item)
            self._list.setItemWidget(
                item, self._row_widget(command, command.name in pin_set)
            )

        rows = min(12, max(4, self._list.count()))
        self._list.setMinimumHeight(rows * 28)
        self.adjustSize()

    def _row_widget(self, command: RibbonCommand, pinned: bool) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(2, 1, 2, 1)
        layout.setSpacing(4)

        pin_btn = QToolButton()
        pin_btn.setObjectName("NeoRibbon_pin")
        pin_btn.setAutoRaise(True)
        pin_btn.setCheckable(True)
        pin_btn.setChecked(pinned)
        pin_btn.setIcon(self._pin_filled if pinned else self._pin_outline)
        pin_btn.setIconSize(QSize(14, 14))
        pin_btn.setFixedSize(22, 22)
        pin_btn.setToolTip("Unpin from focus" if pinned else "Pin to focus strip")
        pin_btn.toggled.connect(
            lambda checked, n=command.name, b=pin_btn: self._toggle_pin(n, checked, b)
        )
        layout.addWidget(pin_btn)

        run_btn = QToolButton()
        run_btn.setObjectName(f"NeoRibbon_list_btn_{command.name}")
        run_btn.setAutoRaise(True)
        run_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        run_btn.setIcon(_icon_for(command))
        run_btn.setIconSize(LIST_ICON)
        run_btn.setText(command.text or command.name)
        tip = command.tooltip or command.text or command.name
        count = usage.usage_count(command.name)
        if count:
            tip = f"{tip}  ·  used {count}×"
        if pinned:
            tip = f"{tip}  ·  pinned"
        run_btn.setToolTip(tip)
        run_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        run_btn.clicked.connect(lambda _c=False, n=command.name: self._activate(n))
        layout.addWidget(run_btn, 1)

        help_btn = QToolButton()
        help_btn.setObjectName("NeoRibbon_help")
        help_btn.setAutoRaise(True)
        help_page = _help_page_for_command(command.name)
        if self._help_icon and not self._help_icon.isNull():
            help_btn.setIcon(self._help_icon)
            help_btn.setIconSize(QSize(14, 14))
            help_btn.setText("")
        else:
            help_btn.setText("?")
        help_btn.setFixedSize(22, 22)
        help_btn.setToolTip(f"Open wiki help in browser:\n{help_page}")
        help_btn.clicked.connect(
            lambda _c=False, n=command.name: self._open_help(n)
        )
        layout.addWidget(help_btn)
        return row

    def _open_help(self, command_name: str) -> None:
        # Keep the list open so users can browse several help pages.
        _open_command_help(command_name)

    def _toggle_pin(self, command_name: str, pinned: bool, button: QToolButton) -> None:
        prefs.set_pinned(self._section, command_name, pinned)
        button.setIcon(self._pin_filled if pinned else self._pin_outline)
        button.setToolTip("Unpin from focus" if pinned else "Pin to focus strip")
        self._pins_dirty = True

    def _activate(self, command_name: str) -> None:
        self.close()
        _run_command(command_name)

    def closeEvent(self, event) -> None:  # noqa: N802
        # Refresh focus strip after the list closes so pinning does not dismiss it.
        if self._pins_dirty and self._on_changed:
            self._pins_dirty = False
            self._on_changed()
        super().closeEvent(event)

class RibbonGroup(QWidget):
    """
    One toolbar as an Office-style group.

    Focus strip shows pinned + most-used commands. A bottom ▾ opens the full
    labeled command list with pin controls.
    """

    def __init__(
        self,
        panel: RibbonPanel,
        style: DensityStyle,
        on_hide: Optional[Callable[[str], None]] = None,
        on_changed: Optional[Callable[[], None]] = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._panel = panel
        self._panel_name = panel.name
        self._style = style
        self._on_hide = on_hide
        self._on_changed = on_changed
        self._popup: SectionListPopup | None = None
        self.setObjectName(f"NeoRibbon_group_{panel.name}")
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(style.ribbon_height)

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 2, 4, 0)
        root.setSpacing(0)

        body = QWidget()
        body.setFixedHeight(style.content_height)
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(2, 2, 2, 2)
        body_layout.setSpacing(2)
        body_layout.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )

        limit = prefs.visible_per_section()
        focus = usage.focus_commands(panel.name, list(panel.commands), limit)
        self._fill_visible(body_layout, focus)
        body_layout.addStretch(1)
        root.addWidget(body)
        root.addWidget(self._title_bar(panel.name))

    def _fill_visible(
        self, layout: QHBoxLayout, commands: list[RibbonCommand]
    ) -> None:
        if not commands:
            return

        style = self._style
        start = 0
        if prefs.promote_large():
            layout.addWidget(self._large_button(commands[0]))
            start = 1

        rest = commands[start:]
        rows = style.rows
        for index in range(0, len(rest), rows):
            column_cmds = rest[index : index + rows]
            column = QWidget()
            grid = QGridLayout(column)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(1)
            grid.setVerticalSpacing(1)
            for row, command in enumerate(column_cmds):
                grid.addWidget(self._small_button(command), row, 0)
            if len(column_cmds) < rows:
                grid.setRowStretch(rows - 1, 1)
            layout.addWidget(column)

    def _title_bar(self, name: str) -> QWidget:
        style = self._style
        bar = QWidget()
        bar.setObjectName("NeoRibbon_group_footer")
        bar.setFixedHeight(style.title_height)
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        # Match FreeCAD toolbar / ribbon button label font exactly.
        ref = QToolButton()
        label_font = QFont(ref.font())

        hide_btn = QToolButton()
        hide_btn.setObjectName("NeoRibbon_hide_section")
        hide_btn.setAutoRaise(True)
        hide_btn.setText("×")
        hide_btn.setFont(label_font)
        hide_btn.setToolTip(f"Hide section “{name}”")
        hide_btn.setFixedSize(16, style.title_height)
        hide_btn.clicked.connect(self._hide_section)
        row.addWidget(hide_btn, 0)

        title = QLabel(_short_label(name, 14))
        title.setObjectName("NeoRibbon_group_title")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        title.setFont(label_font)
        title.setToolTip(name)
        row.addWidget(title, 1)

        drop_btn = QToolButton()
        drop_btn.setObjectName("NeoRibbon_section_drop")
        drop_btn.setAutoRaise(True)
        drop_btn.setText("▾")
        drop_btn.setFont(label_font)
        drop_btn.setToolTip(
            f"Show all “{name}” commands as a list (with pin to focus)"
        )
        drop_btn.setFixedSize(16, style.title_height)
        drop_btn.clicked.connect(self._open_section_list)
        row.addWidget(drop_btn, 0)

        bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        bar.customContextMenuRequested.connect(
            lambda pos, b=bar: self._title_menu(b.mapToGlobal(pos))
        )
        return bar

    def _open_section_list(self) -> None:
        if self._popup is not None:
            self._popup.close()
            self._popup = None

        commands = usage.named_commands(list(self._panel.commands))
        popup = SectionListPopup(
            self._panel_name,
            commands,
            on_changed=self._on_changed,
            parent=self.window(),
        )
        self._popup = popup

        # Anchor under this group’s bottom edge.
        origin = self.mapToGlobal(QPoint(0, self.height()))
        popup.move(origin)
        popup.show()
        popup.raise_()
        popup.activateWindow()

    def _hide_section(self) -> None:
        prefs.set_section_hidden(self._panel_name, True)
        if self._on_hide:
            self._on_hide(self._panel_name)

    def _title_menu(self, global_pos) -> None:
        menu = QMenu(self)
        theme.apply_menu_theme(menu)
        menu.addAction(f"Hide “{self._panel_name}”", self._hide_section)
        menu.addAction("Show all commands…", self._open_section_list)
        menu.exec(global_pos)

    def _large_button(self, command: RibbonCommand) -> QToolButton:
        style = self._style
        button = QToolButton()
        button.setObjectName(f"NeoRibbon_btn_{command.name}")
        button.setAutoRaise(True)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        button.setIcon(_icon_for(command))
        button.setIconSize(style.large_icon)
        label = _short_label(command.text or command.name, style.label_chars + 1)
        if prefs.is_pinned(self._panel_name, command.name):
            label = "• " + label
        button.setText(label)
        tip = command.tooltip or command.text or command.name
        count = usage.usage_count(command.name)
        if count:
            tip = f"{tip}  ·  used {count}×"
        if prefs.is_pinned(self._panel_name, command.name):
            tip = f"{tip}  ·  pinned"
        button.setToolTip(tip)
        button.setFixedHeight(style.content_height - 4)
        button.setMinimumWidth(style.large_btn_min_width)
        button.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self._wire_command_button(button, command)
        return button

    def _small_button(self, command: RibbonCommand) -> QToolButton:
        style = self._style
        button = QToolButton()
        button.setObjectName(f"NeoRibbon_btn_{command.name}")
        button.setAutoRaise(True)
        button.setIcon(_icon_for(command))
        button.setIconSize(style.small_icon)
        tip = command.tooltip or command.text or command.name
        count = usage.usage_count(command.name)
        pinned = prefs.is_pinned(self._panel_name, command.name)
        if count:
            tip = f"{tip}  ·  used {count}×"
        if pinned:
            tip = f"{tip}  ·  pinned"
        if style.small_show_text:
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            text = _short_label(command.text or command.name, style.label_chars)
            if pinned:
                text = "• " + text
            button.setText(text)
            button.setFixedHeight(style.small_btn_height)
            button.setMinimumWidth(style.small_btn_min_width)
        else:
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setText("")
            button.setFixedSize(style.small_btn_min_width + 2, style.small_btn_height)
        button.setToolTip(tip)
        self._wire_command_button(button, command)
        return button

    def _wire_command_button(self, button: QToolButton, command: RibbonCommand) -> None:
        """Single-action click, or menu for FreeCAD compound commands."""
        actions = command_actions_meta(command.name)
        if command.action_count > 1 and len(actions) > 1:
            button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
            menu = QMenu(button)
            theme.apply_menu_theme(menu)
            for index, text, tip in actions:
                action = menu.addAction(_icon_for(command, index), text)
                action.setToolTip(tip)
                action.triggered.connect(
                    lambda _c=False, n=command.name, i=index: _run_command(n, i)
                )
            button.setMenu(menu)
            # Primary click runs the first action (e.g. New Sketch).
            button.clicked.connect(
                lambda _c=False, n=command.name: _run_command(n, 0)
            )
        else:
            button.clicked.connect(
                lambda _c=False, n=command.name: _run_command(n, 0)
            )


class RibbonBar(QWidget):
    """Horizontal Office-style ribbon: groups side-by-side, not one tab per toolbar."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("NeoRibbonBar")
        self._style = density_style()
        self.setMinimumHeight(self._style.ribbon_height)
        self.setMaximumHeight(self._style.ribbon_height + 32)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea(self)
        self._scroll.setObjectName("NeoRibbonScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setMinimumHeight(self._style.ribbon_height)

        self._strip = QWidget()
        self._strip.setObjectName("NeoRibbonStrip")
        self._strip.setMinimumHeight(self._style.ribbon_height)
        self._strip_layout = QHBoxLayout(self._strip)
        self._strip_layout.setContentsMargins(2, 0, 2, 0)
        self._strip_layout.setSpacing(0)
        self._strip_layout.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self._scroll.setWidget(self._strip)
        outer.addWidget(self._scroll)

        self._all_panels: list[RibbonPanel] = []
        self._last_signature: tuple | None = None
        self._retheme_pending = False
        self._applying_theme = True
        try:
            self._theme_colors = theme.apply_widget_theme(self)
        finally:
            self._applying_theme = False

        sb = self._scroll.horizontalScrollBar()
        sb.rangeChanged.connect(lambda *_args: self._apply_dynamic_height())
        self._apply_dynamic_height()

        try:
            Gui.getMainWindow().installEventFilter(self)
        except Exception:
            pass

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if not hasattr(self, "_applying_theme"):
            return
        if self._applying_theme or self._retheme_pending:
            return
        try:
            etype = event.type()
        except Exception:
            return
        if etype in (
            QEvent.Type.StyleChange,
            QEvent.Type.PaletteChange,
            QEvent.Type.ApplicationPaletteChange,
        ):
            self._retheme_pending = True
            QTimer.singleShot(50, self._reapply_theme)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if not hasattr(self, "_applying_theme"):
            return False
        if self._applying_theme or self._retheme_pending:
            return False
        try:
            etype = event.type()
        except Exception:
            return False
        if etype in (
            QEvent.Type.StyleChange,
            QEvent.Type.PaletteChange,
            QEvent.Type.ApplicationPaletteChange,
        ):
            self._retheme_pending = True
            QTimer.singleShot(50, self._reapply_theme)
        return False

    def _reapply_theme(self) -> None:
        self._retheme_pending = False
        self._applying_theme = True
        try:
            self._theme_colors = theme.apply_widget_theme(self)
            self.refresh(force=True)
        finally:
            # Allow style events again after our stylesheet settles.
            QTimer.singleShot(0, self._end_theme_apply)

    def _end_theme_apply(self) -> None:
        self._applying_theme = False

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_dynamic_height()

    def _scrollbar_extra(self) -> int:
        """Height to reserve under the ribbon so the h-scrollbar does not cover labels."""
        sb = self._scroll.horizontalScrollBar()
        need = sb.maximum() > sb.minimum()
        if not need:
            viewport_w = self._scroll.viewport().width()
            strip_w = self._strip.sizeHint().width()
            if viewport_w > 0 and strip_w > viewport_w:
                need = True
        if not need:
            return 0
        hint = sb.sizeHint().height()
        if sb.isVisible() and sb.height() > 0:
            return max(hint, sb.height())
        return max(hint, 14)

    def _apply_dynamic_height(self) -> None:
        extra = self._scrollbar_extra()
        base = self._style.ribbon_height if hasattr(self, "_style") else RIBBON_HEIGHT
        total = base + extra
        if self.height() == total and self._scroll.height() == total:
            # Still notify dock in case it drifted.
            self._sync_dock_height(total)
            return
        self.setFixedHeight(total)
        self._scroll.setFixedHeight(total)
        self._sync_dock_height(total)

    def _sync_dock_height(self, ribbon_height: int) -> None:
        parent = self.parent()
        while parent is not None:
            if isinstance(parent, RibbonDock) or parent.objectName() == "NeoRibbonDock":
                dock_h = ribbon_height + 2
                parent.setMinimumHeight(dock_h)
                parent.setMaximumHeight(dock_h)
                parent.setFixedHeight(dock_h)
                try:
                    parent.setPalette(self.palette())
                except Exception:
                    pass
                return
            parent = parent.parent()

    def clear(self) -> None:
        while self._strip_layout.count():
            item = self._strip_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._last_signature = None

    def refresh(self, force: bool = False) -> None:
        panels = active_panels()
        self._all_panels = panels
        style = density_style()
        density = style.name
        promote = prefs.promote_large()
        hidden = prefs.hidden_sections()
        limit = prefs.visible_per_section()
        pins = prefs.pins_signature()
        focus_sig = tuple(
            tuple(
                cmd.name
                for cmd in usage.focus_commands(
                    panel.name, list(panel.commands), limit
                )
            )
            for panel in panels
            if panel.name not in hidden
        )
        signature = (
            density,
            promote,
            limit,
            tuple(sorted(hidden)),
            pins,
            focus_sig,
            active_workbench_name(),
            tuple(
                (panel.name, tuple(cmd.name for cmd in panel.commands))
                for panel in panels
            ),
        )
        if not force and signature == self._last_signature:
            return
        self.clear()
        self._last_signature = signature
        self._style = style
        self.setMinimumHeight(style.ribbon_height)
        self.setMaximumHeight(style.ribbon_height + 32)
        self._scroll.setMinimumHeight(style.ribbon_height)
        self._strip.setMinimumHeight(style.ribbon_height)
        # Keep colors in sync when FreeCAD theme tokens / palette change.
        self._theme_colors = theme.apply_widget_theme(self)

        # Workbench selector first — classic toolbar combo is hidden with toolbars.
        self._strip_layout.addWidget(WorkbenchSelector(style))
        sep = QFrame()
        sep.setObjectName("NeoRibbon_group_sep")
        sep.setFrameShape(QFrame.Shape.NoFrame)
        sep.setFixedWidth(1)
        sep.setFixedHeight(style.ribbon_height - 8)
        self._strip_layout.addWidget(sep)

        visible_panels = [p for p in panels if p.name not in hidden]
        for index, panel in enumerate(visible_panels):
            if index:
                sep = QFrame()
                sep.setObjectName("NeoRibbon_group_sep")
                sep.setFrameShape(QFrame.Shape.NoFrame)
                sep.setFixedWidth(1)
                sep.setFixedHeight(style.ribbon_height - 8)
                self._strip_layout.addWidget(sep)
            self._strip_layout.addWidget(
                RibbonGroup(
                    panel,
                    style,
                    on_hide=self._on_section_hidden,
                    on_changed=self._on_pins_changed,
                )
            )

        self._strip_layout.addWidget(self._sections_button(panels, hidden, style))
        self._strip_layout.addStretch(1)
        QTimer.singleShot(0, self._apply_dynamic_height)

    def _on_section_hidden(self, _name: str) -> None:
        self.refresh(force=True)

    def _on_pins_changed(self) -> None:
        self.refresh(force=True)

    def _sections_button(
        self,
        panels: list[RibbonPanel],
        hidden: frozenset[str],
        style: DensityStyle,
    ) -> QToolButton:
        button = QToolButton()
        button.setObjectName("NeoRibbon_sections")
        button.setAutoRaise(True)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        button.setText("Sections ▾")
        button.setToolTip("Show or hide ribbon sections")
        button.setFixedHeight(style.content_height - 4)
        theme.apply_chrome_palette(button)

        menu = QMenu(button)
        theme.apply_menu_theme(menu)
        if not panels:
            empty = menu.addAction("No sections")
            empty.setEnabled(False)
        for panel in panels:
            action = menu.addAction(panel.name)
            action.setCheckable(True)
            action.setChecked(panel.name not in hidden)
            action.toggled.connect(
                lambda checked, n=panel.name: self._set_section_visible(n, checked)
            )
        if hidden:
            menu.addSeparator()
            show_all = menu.addAction("Show all sections")
            show_all.triggered.connect(self._show_all_sections)
        button.setMenu(menu)
        return button

    def _set_section_visible(self, name: str, visible: bool) -> None:
        prefs.set_section_hidden(name, not visible)
        self.refresh(force=True)

    def _show_all_sections(self) -> None:
        prefs.set_hidden_sections([])
        self.refresh(force=True)

    @property
    def panel_count(self) -> int:
        count = 0
        for i in range(self._strip_layout.count()):
            widget = self._strip_layout.itemAt(i).widget()
            if widget is None:
                continue
            name = widget.objectName()
            if name.startswith("NeoRibbon_group_") and name != "NeoRibbon_group_sep":
                count += 1
        return count


class RibbonDock(QDockWidget):
    """Top dock hosting the ribbon without bulky dock chrome."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("NeoRibbon", parent)
        self.setObjectName("NeoRibbonDock")
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        self.setAllowedAreas(
            Qt.DockWidgetArea.TopDockWidgetArea | Qt.DockWidgetArea.BottomDockWidgetArea
        )
        self.setTitleBarWidget(QWidget(self))
        self.ribbon = RibbonBar(self)
        self.setWidget(self.ribbon)
        # Height is driven dynamically by RibbonBar when a scrollbar appears.
        h = density_style().ribbon_height
        self.setMinimumHeight(h + 2)
        self.setMaximumHeight(h + 34)
        self.setFixedHeight(h + 2)

    def refresh(self, force: bool = False) -> None:
        self.ribbon.refresh(force=force)
