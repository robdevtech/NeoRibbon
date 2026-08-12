# SPDX-License-Identifier: LGPL-2.1-or-later
"""Preference access for NeoRibbon."""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from typing import Iterable

import FreeCAD as App

PARAM_PATH = "User parameter:BaseApp/Preferences/Mod/NeoRibbon"

BUTTON_SIZES = ("small", "medium", "large")
DEFAULT_BUTTON_SIZE = "medium"
DEFAULT_VISIBLE_PER_SECTION = 6

# Keep one ParamGet wrapper alive. ParameterGrpPy::~ParameterGrpPy Detach()es
# observers, so Attach() on a temporary App.ParamGet(...) is a no-op after GC.
_group_handle = None


def addon_root() -> str:
    """Addon Mod root (package.xml / Resources live here; freecad/NeoRibbon/ is nested)."""
    # freecad/NeoRibbon/prefs.py → parents[2] = Mod / repo root
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def addon_version() -> str:
    """Version from package.xml at Mod root — cannot drift from the package."""
    path = os.path.join(addon_root(), "package.xml")
    try:
        root = ET.parse(path).getroot()
        tag = "version"
        if root.tag.startswith("{") and "}" in root.tag:
            tag = f"{root.tag.split('}')[0]}}}version"
        el = root.find(tag)
        if el is not None and (el.text or "").strip():
            return el.text.strip()
    except Exception:
        pass
    return ""


def _group():
    global _group_handle
    if _group_handle is None:
        _group_handle = App.ParamGet(PARAM_PATH)
    return _group_handle


def param_group():
    """Long-lived handle for attaching preference observers."""
    return _group()


def is_enabled() -> bool:
    group = _group()
    try:
        contents = group.GetContents() or ()
    except Exception:
        contents = ()
    for item in contents:
        try:
            kind, name, value = item[0], item[1], item[2]
        except Exception:
            continue
        if name != "Enabled":
            continue
        if kind == "Boolean":
            return bool(value)
        if kind == "Integer":
            return bool(int(value))
        if kind == "String":
            return str(value).strip().lower() not in ("0", "false", "no", "off", "")
    return bool(group.GetBool("Enabled", True))


def set_enabled(value: bool) -> None:
    _group().SetBool("Enabled", bool(value))


def button_size_index() -> int:
    """0=small, 1=medium, 2=large — PrefComboBox stores the combo index as Int."""
    group = _group()
    int_idx: int | None = None
    str_idx: int | None = None
    try:
        contents = group.GetContents() or ()
    except Exception:
        contents = ()
    for item in contents:
        try:
            kind, name, value = item[0], item[1], item[2]
        except Exception:
            continue
        if name != "ButtonSize":
            continue
        if kind == "Integer":
            idx = int(value)
            if 0 <= idx < len(BUTTON_SIZES):
                int_idx = idx
        elif kind == "String":
            size = str(value).strip().lower()
            if size in BUTTON_SIZES:
                str_idx = BUTTON_SIZES.index(size)
    # Int wins (Edit → Preferences PrefComboBox). String is legacy PrefLineEdit.
    if int_idx is not None:
        if str_idx is not None:
            try:
                group.RemString("ButtonSize")
            except Exception:
                pass
        return int_idx
    if str_idx is not None:
        # Migrate legacy string → int so PrefComboBox stays in sync.
        try:
            group.RemString("ButtonSize")
        except Exception:
            pass
        group.SetInt("ButtonSize", str_idx)
        return str_idx
    idx = int(group.GetInt("ButtonSize", -1))
    if 0 <= idx < len(BUTTON_SIZES):
        return idx
    size = group.GetString("ButtonSize", DEFAULT_BUTTON_SIZE).strip().lower()
    if size in BUTTON_SIZES:
        return BUTTON_SIZES.index(size)
    return BUTTON_SIZES.index(DEFAULT_BUTTON_SIZE)


def button_size() -> str:
    return BUTTON_SIZES[button_size_index()]


def set_button_size(value: str) -> None:
    size = value.lower()
    if size not in BUTTON_SIZES:
        raise ValueError(f"Invalid button size: {value}")
    group = _group()
    # Drop legacy string entry so it cannot override the PrefComboBox int.
    try:
        group.RemString("ButtonSize")
    except Exception:
        pass
    group.SetInt("ButtonSize", BUTTON_SIZES.index(size))


def clear_legacy_hide_menubar() -> None:
    """Drop obsolete HideMenubar param from older NeoRibbon versions."""
    group = _group()
    try:
        group.RemBool("HideMenubar")
    except Exception:
        try:
            group.SetBool("HideMenubar", False)
        except Exception:
            pass


def promote_large() -> bool:
    """Show the first focus command as a large icon in each section."""
    return _group().GetBool("PromoteLarge", True)


def set_promote_large(value: bool) -> None:
    _group().SetBool("PromoteLarge", bool(value))


def toggle_promote_large() -> bool:
    """Toggle large-icon promotion. Returns the new value."""
    value = not promote_large()
    set_promote_large(value)
    return value


def show_button_labels() -> bool:
    """Show text labels beside/under focus-strip icons (section lists always labeled)."""
    return _group().GetBool("ShowButtonLabels", True)


def set_show_button_labels(value: bool) -> None:
    _group().SetBool("ShowButtonLabels", bool(value))


def toggle_show_button_labels() -> bool:
    """Toggle focus-strip text labels. Returns the new value."""
    value = not show_button_labels()
    set_show_button_labels(value)
    return value


def visible_per_section() -> int:
    value = int(_group().GetInt("VisiblePerSection", DEFAULT_VISIBLE_PER_SECTION))
    return max(1, min(24, value))


def set_visible_per_section(value: int) -> None:
    _group().SetInt("VisiblePerSection", max(1, min(24, int(value))))


def ignored_toolbars() -> frozenset[str]:
    raw = _group().GetString("IgnoredToolbars", "")
    names = {part.strip() for part in raw.split(";") if part.strip()}
    return frozenset(names)


def set_ignored_toolbars(names: Iterable[str]) -> None:
    cleaned = sorted({name.strip() for name in names if name and name.strip()})
    _group().SetString("IgnoredToolbars", ";".join(cleaned))


def ignored_toolbars_text() -> str:
    return _group().GetString("IgnoredToolbars", "")


def set_ignored_toolbars_text(text: str) -> None:
    set_ignored_toolbars(text.split(";"))


def hidden_sections() -> frozenset[str]:
    raw = _group().GetString("HiddenSections", "")
    return frozenset(part.strip() for part in raw.split(";") if part.strip())


def set_hidden_sections(names: Iterable[str]) -> None:
    cleaned = sorted({name.strip() for name in names if name and name.strip()})
    _group().SetString("HiddenSections", ";".join(cleaned))


def is_section_hidden(name: str) -> bool:
    return name in hidden_sections()


def set_section_hidden(name: str, hidden: bool) -> None:
    current = set(hidden_sections())
    if hidden:
        current.add(name)
    else:
        current.discard(name)
    set_hidden_sections(current)


def toggle_section_hidden(name: str) -> bool:
    """Toggle section visibility. Returns True if now hidden."""
    hidden = not is_section_hidden(name)
    set_section_hidden(name, hidden)
    return hidden


def _section_order_group():
    return App.ParamGet(f"{PARAM_PATH}/SectionOrder")


def _section_order_key(workbench: str) -> str:
    return (workbench or "workbench").replace("/", "_").replace("\\", "_")[:200]


def section_order(workbench: str | None) -> list[str]:
    """Saved ribbon section names for a workbench, or empty (use workbench order)."""
    if not workbench:
        return []
    raw = _section_order_group().GetString(_section_order_key(workbench), "")
    return [part.strip() for part in raw.split(";") if part.strip()]


def set_section_order(workbench: str | None, names: Iterable[str]) -> None:
    if not workbench:
        return
    seen: set[str] = set()
    ordered: list[str] = []
    for name in names:
        name = (name or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        ordered.append(name)
    _section_order_group().SetString(_section_order_key(workbench), ";".join(ordered))


def clear_section_order(workbench: str | None) -> None:
    """Drop custom order so the workbench toolbar order is used again."""
    if not workbench:
        return
    group = _section_order_group()
    key = _section_order_key(workbench)
    try:
        group.RemString(key)
    except Exception:
        group.SetString(key, "")


def apply_section_order(workbench: str | None, names: Iterable[str]) -> list[str]:
    """
    Reorder *names* using a saved per-workbench list.

    Unknown/new names keep their relative order and append after saved ones.
    An empty saved list means “use the given (workbench) order”.
    """
    current = [name for name in names if name]
    saved = section_order(workbench)
    if not saved:
        return current
    known = set(current)
    seen: set[str] = set()
    ordered: list[str] = []
    for name in saved:
        if name in known and name not in seen:
            ordered.append(name)
            seen.add(name)
    for name in current:
        if name not in seen:
            ordered.append(name)
            seen.add(name)
    return ordered


def _pins_group():
    return App.ParamGet(f"{PARAM_PATH}/Pins")


def _pin_key(section: str) -> str:
    # Param entry names should stay simple.
    return section.replace("/", "_").replace("\\", "_")[:200] or "section"


def pinned_commands(section: str) -> list[str]:
    raw = _pins_group().GetString(_pin_key(section), "")
    return [part.strip() for part in raw.split(";") if part.strip()]


def set_pinned_commands(section: str, names: Iterable[str]) -> None:
    # Preserve order, drop duplicates.
    seen: set[str] = set()
    ordered: list[str] = []
    for name in names:
        name = (name or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        ordered.append(name)
    _pins_group().SetString(_pin_key(section), ";".join(ordered))


def is_pinned(section: str, command: str) -> bool:
    return command in pinned_commands(section)


def set_pinned(section: str, command: str, pinned: bool) -> None:
    current = pinned_commands(section)
    if pinned:
        if command not in current:
            current.append(command)
    else:
        current = [name for name in current if name != command]
    set_pinned_commands(section, current)


def toggle_pin(section: str, command: str) -> bool:
    """Toggle pin. Returns True if now pinned."""
    pinned = not is_pinned(section, command)
    set_pinned(section, command, pinned)
    return pinned


def pins_signature() -> tuple:
    """Compact snapshot of all pins for ribbon rebuild detection."""
    group = _pins_group()
    try:
        contents = group.GetContents()
    except Exception:
        return ()
    # GetContents returns list of tuples like ('String', name, value) in FreeCAD.
    entries = []
    for item in contents or ():
        try:
            if item[0] == "String":
                entries.append((item[1], item[2]))
        except Exception:
            continue
    return tuple(sorted(entries))
