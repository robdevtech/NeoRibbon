# SPDX-License-Identifier: LGPL-2.1-or-later
"""Per-command usage counts and focus ranking for ribbon buttons."""

from __future__ import annotations

import FreeCAD as App

from neoribbon import prefs
from neoribbon.prefs import PARAM_PATH

_USAGE_PATH = f"{PARAM_PATH}/Usage"


def _group():
    return App.ParamGet(_USAGE_PATH)


def usage_count(command_name: str) -> int:
    if not command_name:
        return 0
    return int(_group().GetInt(command_name, 0))


def record_use(command_name: str) -> None:
    if not command_name:
        return
    group = _group()
    group.SetInt(command_name, group.GetInt(command_name, 0) + 1)


def named_commands(commands: list) -> list:
    return [cmd for cmd in commands if getattr(cmd, "name", "")]


# Commands that should stay near the front of a section's focus strip.
PRIORITY_COMMANDS = frozenset(
    {
        "PartDesign_CompSketches",
        "Sketcher_NewSketch",
        "PartDesign_Body",
    }
)


def rank_commands(commands: list) -> list:
    """Sort named commands by priority, then usage (desc), then original order."""
    named = [
        (index, cmd)
        for index, cmd in enumerate(commands)
        if getattr(cmd, "name", "")
    ]
    named.sort(
        key=lambda item: (
            0 if item[1].name in PRIORITY_COMMANDS else 1,
            -usage_count(item[1].name),
            item[0],
        )
    )
    return [cmd for _, cmd in named]


def focus_commands(section: str, commands: list, limit: int) -> list:
    """
    Commands for the focus strip: pinned first (pin order), then by usage.

    All valid pins are included even when that exceeds ``limit``. Extra slots
    up to ``limit`` are filled from usage ranking.
    """
    named = named_commands(commands)
    by_name = {cmd.name: cmd for cmd in named}
    pinned_names = [n for n in prefs.pinned_commands(section) if n in by_name]

    focus: list = []
    seen: set[str] = set()
    for name in pinned_names:
        focus.append(by_name[name])
        seen.add(name)

    target = max(int(limit), len(pinned_names))
    for cmd in rank_commands(named):
        if len(focus) >= target:
            break
        if cmd.name in seen:
            continue
        focus.append(cmd)
        seen.add(cmd.name)
    return focus
