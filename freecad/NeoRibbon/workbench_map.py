# SPDX-License-Identifier: LGPL-2.1-or-later
"""Lazy mapping of the active workbench toolbars to ribbon panels."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import FreeCAD as App
import FreeCADGui as Gui

from freecad.NeoRibbon import prefs

# FreeCAD ships bad metadata for some compound commands (wrong menuText / empty pixmap).
_COMMAND_LABEL_FIXES = {
    "PartDesign_CompSketches": "New Sketch",
}


@dataclass(frozen=True)
class RibbonCommand:
    """One ribbon button.

    Compound FreeCAD commands (Rectangle, Arc, …) expose several QActions.
    *action_index* selects which child to run; 0 is the default/parent.
    """

    name: str
    text: str = ""
    tooltip: str = ""
    pixmap: str = ""
    action_count: int = 0
    action_index: int = 0

    def ident(self) -> str:
        """Stable id for pins/usage. Children use ``name::index``."""
        if self.action_index:
            return f"{self.name}::{self.action_index}"
        return self.name


@dataclass(frozen=True)
class RibbonPanel:
    """One ribbon tab/panel = one FreeCAD toolbar."""

    name: str
    commands: tuple[RibbonCommand, ...] = field(default_factory=tuple)


def _command_actions(command) -> list:
    try:
        actions = command.getAction()
        return list(actions) if actions else []
    except Exception:
        return []


def _command_meta(command_name: str) -> RibbonCommand:
    """Resolve label/icon from the FreeCAD command registry (and actions)."""
    text = command_name
    tooltip = ""
    pixmap = ""
    action_count = 0
    try:
        command = Gui.Command.get(command_name)
    except Exception as exc:  # noqa: BLE001
        App.Console.PrintWarning(
            f"NeoRibbon: Gui.Command.get({command_name!r}) failed: {exc}\n"
        )
        return RibbonCommand(name=command_name, text=text)

    if command is None:
        return RibbonCommand(name=command_name, text=text)

    try:
        info = command.getInfo() or {}
    except Exception as exc:  # noqa: BLE001
        App.Console.PrintWarning(
            f"NeoRibbon: getInfo({command_name!r}) failed: {exc}\n"
        )
        return RibbonCommand(name=command_name, text=text)

    menu_text = (info.get("menuText") or "").replace("&", "").strip()
    if menu_text:
        text = menu_text
    tooltip = (info.get("toolTip") or info.get("statusTip") or text).strip()
    pixmap = (info.get("pixmap") or "").strip()

    actions = _command_actions(command)
    action_count = len(actions)
    if actions:
        action0 = actions[0]
        action_text = (action0.text() or "").replace("&", "").strip()
        # Prefer the first action when FreeCAD metadata is empty/wrong
        # (notably PartDesign_CompSketches reports "Create Datum").
        if command_name in _COMMAND_LABEL_FIXES:
            text = _COMMAND_LABEL_FIXES[command_name]
            tooltip = action_text or text
        elif not pixmap or text.lower() in {"create datum", "datum"}:
            if action_text:
                text = action_text
            tip = (action0.toolTip() or "").strip()
            if tip:
                tooltip = tip

    if command_name in _COMMAND_LABEL_FIXES and not tooltip:
        tooltip = _COMMAND_LABEL_FIXES[command_name]

    return RibbonCommand(
        name=command_name,
        text=text,
        tooltip=tooltip,
        pixmap=pixmap,
        action_count=action_count,
        action_index=0,
    )


def expand_command(command: RibbonCommand) -> list[RibbonCommand]:
    """One parent, or one row per child when listing children individually."""
    if prefs.nest_command_children():
        return [command]
    children = command_actions_meta(command.name)
    if len(children) <= 1:
        return [command]
    expanded: list[RibbonCommand] = []
    for index, text, tip in children:
        expanded.append(
            RibbonCommand(
                name=command.name,
                text=text,
                tooltip=tip or text,
                pixmap=command.pixmap,
                action_count=1,
                action_index=index,
            )
        )
    return expanded


def command_action_icon(command_name: str, index: int = 0):
    """QIcon from a FreeCAD command action, or None."""
    try:
        command = Gui.Command.get(command_name)
        if command is None:
            return None
        actions = _command_actions(command)
        if 0 <= index < len(actions):
            icon = actions[index].icon()
            if icon is not None and not icon.isNull():
                return icon
    except Exception:
        return None
    return None


def command_actions_meta(command_name: str) -> list[tuple[int, str, str]]:
    """Return [(index, text, tooltip), ...] for compound FreeCAD commands."""
    result = []
    for index, action in enumerate(command_qactions(command_name)):
        text = (action.text() or "").replace("&", "").strip() or f"Action {index}"
        tip = (action.toolTip() or text).strip()
        result.append((index, text, tip))
    return result


def command_qactions(command_name: str) -> list:
    """Live QAction list for a FreeCAD command, or [] if none exist yet."""
    if not command_name:
        return []
    try:
        command = Gui.Command.get(command_name)
        if command is None:
            return []
        return _command_actions(command)
    except Exception:
        return []


def command_checkable_action(command_name: str, index: int = 0):
    """Return the QAction at *index* when it exists and is checkable."""
    actions = command_qactions(command_name)
    if not (0 <= index < len(actions)):
        return None
    action = actions[index]
    try:
        if action is not None and action.isCheckable():
            return action
    except Exception:
        return None
    return None


def _is_separator(token: str) -> bool:
    return not token or token in {"|", "Separator", "separator"}


def workbench_toolbar_panels() -> list[RibbonPanel]:
    """
    Panels in the active workbench's getToolbarItems() order.

    Never activates other workbenches. Does not apply custom section order.
    """
    ignored = prefs.ignored_toolbars()
    try:
        workbench = Gui.activeWorkbench()
    except Exception as exc:  # noqa: BLE001
        App.Console.PrintWarning(f"NeoRibbon: activeWorkbench failed: {exc}\n")
        return []

    if workbench is None:
        return []

    try:
        name = getattr(workbench, "name", None)
        if callable(name):
            wb_name = name()
        else:
            wb_name = type(workbench).__name__
        if wb_name in (None, "", "NoneWorkbench"):
            return []
    except Exception as exc:  # noqa: BLE001
        App.Console.PrintWarning(f"NeoRibbon: workbench name check failed: {exc}\n")

    try:
        toolbar_items = workbench.getToolbarItems()
    except Exception as exc:  # noqa: BLE001
        App.Console.PrintWarning(f"NeoRibbon: getToolbarItems failed: {exc}\n")
        return []

    if not toolbar_items:
        return []

    panels: list[RibbonPanel] = []
    for toolbar_name, commands in toolbar_items.items():
        if not toolbar_name or toolbar_name in ignored:
            continue
        ribbon_commands: list[RibbonCommand] = []
        for raw in commands or ():
            cmd = str(raw)
            if _is_separator(cmd):
                ribbon_commands.append(RibbonCommand(name=""))
                continue
            if cmd == "Std_Workbench":
                continue
            ribbon_commands.extend(expand_command(_command_meta(cmd)))
        if ribbon_commands:
            panels.append(
                RibbonPanel(name=str(toolbar_name), commands=tuple(ribbon_commands))
            )
    return panels


def active_panels() -> list[RibbonPanel]:
    """
    Panels for the active workbench, with persisted custom section order applied.

    New/unknown toolbars append after saved names. Hidden sections are not
    filtered here — callers omit them when building the visible ribbon.
    """
    panels = workbench_toolbar_panels()
    if not panels:
        return panels
    ordered = prefs.apply_section_order(
        active_workbench_name(), [panel.name for panel in panels]
    )
    by_name = {panel.name: panel for panel in panels}
    return [by_name[name] for name in ordered if name in by_name]


def active_workbench_name() -> Optional[str]:
    try:
        workbench = Gui.activeWorkbench()
        if workbench is None:
            return None
        name = getattr(workbench, "name", None)
        if callable(name):
            value = name()
            if value:
                return str(value)
        menu = str(getattr(workbench, "MenuText", "") or "").replace("&", "")
        for wb_name, wb in Gui.listWorkbenches().items():
            wb_menu = str(getattr(wb, "MenuText", "") or "").replace("&", "")
            if wb_menu and wb_menu == menu:
                return str(wb_name)
        return type(workbench).__name__
    except Exception as exc:  # noqa: BLE001
        App.Console.PrintWarning(f"NeoRibbon: active workbench name failed: {exc}\n")
        return None


def active_workbench_title() -> Optional[str]:
    try:
        workbench = Gui.activeWorkbench()
        if workbench is None:
            return None
        menu = getattr(workbench, "MenuText", None)
        if menu:
            return str(menu).replace("&", "")
        return type(workbench).__name__
    except Exception:
        return None


def workbench_entries() -> list[tuple[str, str, str]]:
    """
    Installed workbenches as (internal_name, menu_text, icon_name).

    Never activates workbenches.
    """
    skip = {"NoneWorkbench", "TestWorkbench"}
    entries: list[tuple[str, str, str]] = []
    try:
        installed = Gui.listWorkbenches() or {}
    except Exception as exc:  # noqa: BLE001
        App.Console.PrintWarning(f"NeoRibbon: listWorkbenches failed: {exc}\n")
        return []

    for wb_name, workbench in installed.items():
        if not wb_name or wb_name in skip:
            continue
        title = str(getattr(workbench, "MenuText", "") or "").replace("&", "").strip()
        if not title or title == "<none>":
            continue
        icon = str(getattr(workbench, "Icon", "") or "").strip()
        entries.append((str(wb_name), title, icon))

    entries.sort(key=lambda item: item[1].lower())
    return entries
