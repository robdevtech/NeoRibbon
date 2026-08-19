# SPDX-License-Identifier: LGPL-2.1-or-later
"""Per-command usage counts and focus ranking for ribbon buttons."""

from __future__ import annotations

import FreeCAD as App

from freecad.NeoRibbon import prefs
from freecad.NeoRibbon.prefs import PARAM_PATH

_USAGE_PATH = f"{PARAM_PATH}/Usage"


def _group():
    return App.ParamGet(_USAGE_PATH)


def _usage_key(command_name: str) -> str:
    # Param entry names should stay simple.
    return (command_name or "").replace("/", "_").replace(":", "_")[:200]


def usage_count(command_name: str) -> int:
    key = _usage_key(command_name)
    if not key:
        return 0
    return int(_group().GetInt(key, 0))


def record_use(command_name: str) -> None:
    key = _usage_key(command_name)
    if not key:
        return
    group = _group()
    group.SetInt(key, group.GetInt(key, 0) + 1)


def _command_ident(cmd) -> str:
    ident = getattr(cmd, "ident", None)
    if callable(ident):
        return str(ident() or "")
    return str(getattr(cmd, "name", "") or "")


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
            -usage_count(_command_ident(item[1])),
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
    by_id = {_command_ident(cmd): cmd for cmd in named}
    pinned_names = [n for n in prefs.pinned_commands(section) if n in by_id]

    focus: list = []
    seen: set[str] = set()
    for name in pinned_names:
        focus.append(by_id[name])
        seen.add(name)

    target = max(int(limit), len(pinned_names))
    for cmd in rank_commands(named):
        if len(focus) >= target:
            break
        ident = _command_ident(cmd)
        if ident in seen:
            continue
        focus.append(cmd)
        seen.add(ident)
    return focus
