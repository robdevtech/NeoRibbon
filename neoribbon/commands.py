# SPDX-License-Identifier: LGPL-2.1-or-later
"""FreeCAD commands registered by NeoRibbon."""

from __future__ import annotations

import os

import FreeCAD as App
import FreeCADGui as Gui

_ICON_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "Resources",
    "icons",
)


def _icon_path(name: str) -> str:
    return os.path.join(_ICON_DIR, name)


class _ToggleCommand:
    def GetResources(self):
        return {
            "Pixmap": _icon_path("NeoRibbon.svg"),
            "MenuText": "Toggle NeoRibbon",
            "ToolTip": "Enable or disable the NeoRibbon dock",
        }

    def Activated(self):
        from neoribbon import bootstrap

        bootstrap.toggle()

    def IsActive(self):
        return True


class _PreferencesCommand:
    def GetResources(self):
        return {
            "Pixmap": _icon_path("NeoRibbon.svg"),
            "MenuText": "NeoRibbon preferences…",
            "ToolTip": "Open NeoRibbon settings",
        }

    def Activated(self):
        from neoribbon.prefs_dialog import open_preferences_dialog

        open_preferences_dialog()

    def IsActive(self):
        return True


class _RestoreToolbarsCommand:
    def GetResources(self):
        return {
            "Pixmap": _icon_path("NeoRibbon.svg"),
            "MenuText": "Restore classic toolbars",
            "ToolTip": "Show FreeCAD toolbars hidden by NeoRibbon",
        }

    def Activated(self):
        from neoribbon import bootstrap

        bootstrap.restore_toolbars()

    def IsActive(self):
        return True


class _ToggleLargeIconCommand:
    def GetResources(self):
        return {
            "Pixmap": _icon_path("NeoRibbon.svg"),
            "MenuText": "Toggle large section icon",
            "ToolTip": "Show or hide the large icon for the first command in each section",
        }

    def Activated(self):
        from neoribbon import bootstrap, prefs

        enabled = prefs.toggle_promote_large()
        bootstrap.apply_prefs()
        state = "on" if enabled else "off"
        App.Console.PrintMessage(f"NeoRibbon large section icon {state}\n")

    def IsActive(self):
        return True


def register() -> None:
    commands = {
        "NeoRibbon_Toggle": _ToggleCommand(),
        "NeoRibbon_Preferences": _PreferencesCommand(),
        "NeoRibbon_ToggleLargeIcon": _ToggleLargeIconCommand(),
        "NeoRibbon_RestoreToolbars": _RestoreToolbarsCommand(),
    }
    for name, command in commands.items():
        try:
            Gui.addCommand(name, command)
        except Exception as exc:  # noqa: BLE001
            App.Console.PrintWarning(f"NeoRibbon: addCommand({name}) failed: {exc}\n")

    try:
        append = getattr(Gui, "appendMenu", None)
        if callable(append):
            append(
                "Tools",
                [
                    "NeoRibbon_Toggle",
                    "NeoRibbon_ToggleLargeIcon",
                    "NeoRibbon_Preferences",
                    "NeoRibbon_RestoreToolbars",
                ],
            )
    except Exception as exc:  # noqa: BLE001
        App.Console.PrintWarning(f"NeoRibbon: appendMenu failed: {exc}\n")
