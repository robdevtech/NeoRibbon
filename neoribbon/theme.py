# SPDX-License-Identifier: LGPL-2.1-or-later
"""Dynamic colors sampled from FreeCAD's theme / widget palette."""

from __future__ import annotations

from dataclasses import dataclass

import FreeCAD as App
import FreeCADGui as Gui
from PySide.QtGui import QColor, QIcon, QPainter, QPalette, QPen, QPixmap, QPolygon
from PySide.QtCore import QPoint, Qt
from PySide.QtWidgets import QMenuBar


@dataclass(frozen=True)
class ThemeColors:
    background: str
    text: str
    muted: str
    border: str
    hover: str
    hover_text: str
    accent: str


def _luminance(color: QColor) -> float:
    r, g, b = color.redF(), color.greenF(), color.blueF()
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
        int(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


def _readable(text: QColor, background: QColor) -> QColor:
    if abs(_luminance(text) - _luminance(background)) >= 0.35:
        return text
    return QColor("#f0f0f0") if _luminance(background) < 0.5 else QColor("#202020")


def _token_exists(group, name: str) -> bool:
    try:
        for entry in group.GetContents() or ():
            if len(entry) >= 2 and entry[1] == name:
                return True
    except Exception:
        pass
    return False


def _token_color(name: str) -> QColor | None:
    """
    Read a FreeCAD theme user-token color when present.

    Tokens are packed as RRGGBBAA (not Qt's AARRGGBB fromRgba).
    """
    try:
        group = App.ParamGet("User parameter:BaseApp/Preferences/Themes/UserTokens/")
        if not _token_exists(group, name):
            return None
        value = int(group.GetUnsigned(name, 0))
        red = (value >> 24) & 0xFF
        green = (value >> 16) & 0xFF
        blue = (value >> 8) & 0xFF
        alpha = value & 0xFF
        if alpha == 0:
            alpha = 255
        color = QColor(red, green, blue, alpha)
        return color if color.isValid() else None
    except Exception:
        return None


def _reference_palette() -> QPalette:
    """
    Palette that matches FreeCAD Light/Dark chrome.

    Do not sample QToolBar/QToolButton: under FreeCAD Light those widgets often
    keep a bogus black QPalette while QSS paints them, which made NeoRibbon go
    dark on an otherwise light UI.
    """
    mw = Gui.getMainWindow()
    if mw is None:
        return QPalette()
    try:
        menubar = mw.menuBar()
    except Exception:
        menubar = None
    if isinstance(menubar, QMenuBar):
        try:
            return menubar.palette()
        except Exception:
            pass
    try:
        return mw.palette()
    except Exception:
        return QPalette()


def resolve_colors() -> ThemeColors:
    """Build a contrast-safe color set from FreeCAD theme tokens + live palette."""
    pal = _reference_palette()
    background = pal.color(QPalette.ColorRole.Window)
    button = pal.color(QPalette.ColorRole.Button)
    # Prefer Window for FreeCAD Light (#f0f0f0); Button is usually the same there.
    chrome = background
    if abs(_luminance(button) - _luminance(background)) > 0.04:
        # Only switch when Button is clearly the chrome surface and still readable.
        chrome = button

    text = _readable(pal.color(QPalette.ColorRole.WindowText), chrome)
    button_text = _readable(pal.color(QPalette.ColorRole.ButtonText), chrome)
    if abs(_luminance(button_text) - _luminance(chrome)) > abs(
        _luminance(text) - _luminance(chrome)
    ):
        text = button_text

    mid = pal.color(QPalette.ColorRole.Mid)
    highlight = pal.color(QPalette.ColorRole.Highlight)
    highlighted_text = _readable(
        pal.color(QPalette.ColorRole.HighlightedText), highlight
    )

    # Soft separators that still read on both light and dark themes.
    border = _mix(mid, chrome, 0.55)
    if abs(_luminance(border) - _luminance(chrome)) < 0.10:
        border = _mix(
            chrome,
            QColor("#ffffff") if _luminance(chrome) < 0.5 else QColor("#000000"),
            0.18,
        )
    muted = _mix(text, chrome, 0.4)
    accent = highlight

    # Prefer FreeCAD theme tokens when the active theme publishes them.
    overrides = {
        "background": _token_color("GeneralBackgroundColor"),
        "text": _token_color("TextForegroundColor"),
        "border": _token_color("GeneralBorderColor"),
        "hover": _token_color("GeneralBackgroundHoverColor"),
        "accent": _token_color("GeneralBorderHoverColor"),
    }
    if overrides["background"] is not None:
        chrome = overrides["background"]
        text = _readable(text, chrome)
        muted = _mix(text, chrome, 0.4)
        border = _mix(border, chrome, 0.2)
    if overrides["text"] is not None:
        text = _readable(overrides["text"], chrome)
        muted = _mix(text, chrome, 0.4)
    if overrides["border"] is not None:
        border = overrides["border"]
    if overrides["hover"] is not None:
        highlight = overrides["hover"]
        highlighted_text = _readable(text, highlight)
    if overrides["accent"] is not None:
        accent = overrides["accent"]

    return ThemeColors(
        background=chrome.name(),
        text=text.name(),
        muted=muted.name(),
        border=border.name(),
        hover=highlight.name(),
        hover_text=highlighted_text.name(),
        accent=accent.name(),
    )


def build_menu_stylesheet(colors: ThemeColors | None = None) -> str:
    """
    Intentionally minimal.

    FreeCAD themes already style QMenu globally. Overriding background here
    made Workbench/Sections menus clash.
    """
    return ""


def apply_chrome_palette(widget) -> None:
    """Copy FreeCAD chrome palette onto a ribbon widget (not popup menus)."""
    try:
        widget.setPalette(_reference_palette())
    except Exception:
        pass


def apply_menu_theme(menu) -> ThemeColors:
    """
    Use FreeCAD's application menu styling instead of ribbon chrome colors.

    Popup QMenus are top-level windows: an empty local stylesheet lets the
    active FreeCAD/OpenTheme QMenu rules paint the correct background.
    """
    colors = resolve_colors()
    try:
        menu.setStyleSheet("")
        menu.setObjectName("NeoRibbon_menu")
    except Exception:
        pass
    return colors


def build_stylesheet(colors: ThemeColors | None = None) -> str:
    colors = colors or resolve_colors()
    return f"""
        QWidget#NeoRibbonBar,
        QWidget#NeoRibbonStrip,
        QScrollArea#NeoRibbonScroll,
        QWidget#NeoRibbon_workbench_selector,
        QWidget#NeoRibbon_group_footer {{
            background: {colors.background};
            color: {colors.text};
        }}
        QLabel#NeoRibbon_group_title {{
            color: {colors.text};
            background: transparent;
            padding: 0 2px;
        }}
        QWidget#NeoRibbon_group_footer {{
            border-top: 1px solid {colors.border};
        }}
        QWidget#NeoRibbon_group_footer_click:hover {{
            background: {colors.hover};
        }}
        QToolButton#NeoRibbon_section_drop,
        QToolButton#NeoRibbon_hide_section,
        QToolButton#NeoRibbon_workbench_button,
        QToolButton#NeoRibbon_sections,
        QToolButton#NeoRibbon_pin,
        QToolButton#NeoRibbon_help {{
            color: {colors.text};
            background: transparent;
            border: none;
            padding: 0px;
        }}
        QToolButton#NeoRibbon_workbench_button {{
            color: {colors.text};
        }}
        QToolButton#NeoRibbon_sections {{
            color: {colors.text};
            padding: 4px;
        }}
        QToolButton#NeoRibbon_workbench_button:hover,
        QToolButton#NeoRibbon_sections:hover,
        QToolButton#NeoRibbon_pin:hover,
        QToolButton#NeoRibbon_help:hover,
        QToolButton[objectName^="NeoRibbon_btn_"]:hover,
        QToolButton[objectName^="NeoRibbon_list_btn_"]:hover {{
            background: {colors.hover};
            color: {colors.hover_text};
            border-radius: 3px;
        }}
        QToolButton[objectName^="NeoRibbon_btn_"]:checked,
        QToolButton[objectName^="NeoRibbon_list_btn_"]:checked {{
            background: {colors.hover};
            color: {colors.hover_text};
            border: 1px solid {colors.accent};
            border-radius: 3px;
        }}
        QToolButton[objectName^="NeoRibbon_btn_"]:checked:hover,
        QToolButton[objectName^="NeoRibbon_list_btn_"]:checked:hover {{
            background: {colors.hover};
            color: {colors.hover_text};
            border: 1px solid {colors.accent};
        }}
        QWidget#NeoRibbon_group_sep {{
            background: {colors.border};
            max-width: 1px;
            margin: 4px 2px;
        }}
        QFrame#NeoRibbon_section_list {{
            background: {colors.background};
            color: {colors.text};
            border: 1px solid {colors.border};
        }}
        QFrame#NeoRibbon_section_list QLabel {{
            color: {colors.text};
            background: transparent;
        }}
        QLabel#NeoRibbon_shortcut {{
            color: {colors.muted};
            background: transparent;
            padding-right: 4px;
            font-size: 11px;
        }}
        QListWidget#NeoRibbon_section_list_view {{
            background: {colors.background};
            color: {colors.text};
            border: none;
        }}
    """


def apply_widget_theme(widget) -> ThemeColors:
    """Copy FreeCAD chrome palette onto a widget and apply dynamic stylesheet."""
    colors = resolve_colors()
    try:
        widget.setPalette(_reference_palette())
    except Exception:
        pass
    widget.setStyleSheet(build_stylesheet(colors))
    return colors


def pin_icons(colors: ThemeColors | None = None) -> tuple[QIcon, QIcon]:
    """Theme-aware outline / filled pin icons (no hardcoded SVG colors)."""
    colors = colors or resolve_colors()
    outline = QColor(colors.muted)
    filled = QColor(colors.accent)
    return _paint_pin(outline, fill=False), _paint_pin(filled, fill=True)


def _paint_pin(color: QColor, fill: bool) -> QIcon:
    size = 16
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(color)
    pen.setWidthF(1.3)
    painter.setPen(pen)
    painter.setBrush(color if fill else Qt.BrushStyle.NoBrush)
    star = QPolygon(
        [
            QPoint(8, 1),
            QPoint(10, 6),
            QPoint(15, 6),
            QPoint(11, 9),
            QPoint(13, 14),
            QPoint(8, 11),
            QPoint(3, 14),
            QPoint(5, 9),
            QPoint(1, 6),
            QPoint(6, 6),
        ]
    )
    painter.drawPolygon(star)
    painter.end()
    icon = QIcon()
    icon.addPixmap(pixmap)
    pixmap2 = QPixmap(size * 2, size * 2)
    pixmap2.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap2)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(pen)
    painter.setBrush(color if fill else Qt.BrushStyle.NoBrush)
    painter.scale(2.0, 2.0)
    painter.drawPolygon(star)
    painter.end()
    icon.addPixmap(pixmap2)
    return icon
