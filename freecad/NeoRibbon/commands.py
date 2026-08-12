# SPDX-License-Identifier: LGPL-2.1-or-later
"""FreeCAD commands registered by NeoRibbon."""

from __future__ import annotations

import os

import FreeCAD as App
import FreeCADGui as Gui

from freecad.NeoRibbon import prefs

_ICON_DIR = os.path.join(prefs.addon_root(), "Resources", "Icons")


def _icon_path(name: str) -> str:
    return os.path.join(_ICON_DIR, name)


class _ToggleCommand:
    def GetResources(self):
        return {
            "Pixmap": _icon_path("NeoRibbon.svg"),
            "MenuText": "Toggle NeoRibbon",
            "ToolTip": "Enable or disable the NeoRibbon dock (Ctrl+Shift+N)",
            "Accel": "Ctrl+Shift+N",
        }

    def Activated(self):
        from freecad.NeoRibbon import bootstrap

        bootstrap.toggle()

    def IsActive(self):
        return True


class _PreferencesCommand:
    def GetResources(self):
        return {
            "Pixmap": _icon_path("NeoRibbon.svg"),
            "MenuText": "NeoRibbon preferences…",
            "ToolTip": "Open NeoRibbon settings (Ctrl+Shift+,)",
            "Accel": "Ctrl+Shift+,",
        }

    def Activated(self):
        from freecad.NeoRibbon.prefs_dialog import open_preferences_dialog

        open_preferences_dialog()

    def IsActive(self):
        return True


class _RestoreToolbarsCommand:
    def GetResources(self):
        return {
            "Pixmap": _icon_path("NeoRibbon.svg"),
            "MenuText": "Restore classic toolbars",
            "ToolTip": (
                "Show FreeCAD toolbars hidden by NeoRibbon "
                "(Ctrl+Shift+R)"
            ),
            "Accel": "Ctrl+Shift+R",
        }

    def Activated(self):
        from freecad.NeoRibbon import bootstrap

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
        from freecad.NeoRibbon import bootstrap, prefs

        enabled = prefs.toggle_promote_large()
        bootstrap.apply_prefs()
        state = "on" if enabled else "off"
        App.Console.PrintMessage(f"NeoRibbon large section icon {state}\n")

    def IsActive(self):
        return True


class _ToggleButtonLabelsCommand:
    def GetResources(self):
        return {
            "Pixmap": _icon_path("NeoRibbon.svg"),
            "MenuText": "Toggle button text labels",
            "ToolTip": (
                "Show or hide text labels on ribbon focus buttons "
                "(section dropdowns always keep labels)"
            ),
        }

    def Activated(self):
        from freecad.NeoRibbon import bootstrap, prefs

        enabled = prefs.toggle_show_button_labels()
        bootstrap.apply_prefs()
        state = "on" if enabled else "off"
        App.Console.PrintMessage(f"NeoRibbon button text labels {state}\n")

    def IsActive(self):
        return True


def register() -> None:
    commands = {
        "NeoRibbon_Toggle": _ToggleCommand(),
        "NeoRibbon_Preferences": _PreferencesCommand(),
        "NeoRibbon_ToggleLargeIcon": _ToggleLargeIconCommand(),
        "NeoRibbon_ToggleButtonLabels": _ToggleButtonLabelsCommand(),
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
                    "NeoRibbon_ToggleButtonLabels",
                    "NeoRibbon_Preferences",
                    "NeoRibbon_RestoreToolbars",
                ],
            )
    except Exception as exc:  # noqa: BLE001
        App.Console.PrintWarning(f"NeoRibbon: appendMenu failed: {exc}\n")
