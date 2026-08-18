# SPDX-License-Identifier: LGPL-2.1-or-later
"""Detect keyboard shortcut collisions with existing FreeCAD / Qt bindings."""

from __future__ import annotations

import FreeCADGui as Gui
from PySide.QtGui import QAction, QKeySequence, QShortcut

from freecad.NeoRibbon import prefs

# Object names owned by NeoRibbon — never treated as foreign conflicts.
# Legacy binders used NeoRibbon_shortcut_<sequence>.
NEORIBBON_COMMAND_NAMES = frozenset(
    {
        "NeoRibbon_Toggle",
        "NeoRibbon_Preferences",
        "NeoRibbon_RestoreToolbars",
    }
)


def _is_our_shortcut_name(name: str) -> bool:
    if not name:
        return False
    if name in prefs.SHORTCUT_OBJECT_NAMES.values():
        return True
    return name.startswith("NeoRibbon_shortcut_")


def _is_our_action_name(name: str, text: str = "") -> bool:
    if name.startswith("NeoRibbon"):
        return True
    return "NeoRibbon" in (text or "")


def normalize_shortcut(text: str) -> str:
    """Return a portable QKeySequence string, or '' if empty/invalid."""
    raw = (text or "").strip()
    if not raw:
        return ""
    try:
        seq = QKeySequence(raw)
    except Exception:
        return raw
    try:
        if hasattr(QKeySequence, "SequenceFormat"):
            out = seq.toString(QKeySequence.SequenceFormat.PortableText)
        elif hasattr(QKeySequence, "PortableText"):
            out = seq.toString(QKeySequence.PortableText)
        else:
            out = seq.toString()
        return (out or "").strip()
    except Exception:
        try:
            return (seq.toString() or "").strip()
        except Exception:
            return raw


def sequences_match(a, b) -> bool:
    """True when two key sequences refer to the same chord."""
    if a is None or b is None:
        return False
    try:
        sa = a if isinstance(a, QKeySequence) else QKeySequence(str(a))
        sb = b if isinstance(b, QKeySequence) else QKeySequence(str(b))
    except Exception:
        return str(a).strip().casefold() == str(b).strip().casefold()
    try:
        if hasattr(sa, "isEmpty") and (sa.isEmpty() or sb.isEmpty()):
            return False
    except Exception:
        pass
    na = normalize_shortcut(sa.toString() if hasattr(sa, "toString") else str(sa))
    nb = normalize_shortcut(sb.toString() if hasattr(sb, "toString") else str(sb))
    if not na or not nb:
        return False
    return na.casefold() == nb.casefold()


def _action_label(action) -> str:
    try:
        text = (action.text() or "").replace("&", "").strip()
    except Exception:
        text = ""
    if text:
        return text
    try:
        name = (action.objectName() or "").strip()
    except Exception:
        name = ""
    return name or "unnamed action"


def _iter_action_sequences(action):
    try:
        if hasattr(action, "shortcuts"):
            for seq in list(action.shortcuts() or []):
                yield seq
            return
    except Exception:
        pass
    try:
        if hasattr(action, "shortcut"):
            yield action.shortcut()
    except Exception:
        return


def find_shortcut_conflicts(mw, sequence: str) -> list[str]:
    """Return human-readable conflict labels for *sequence* on *mw*.

    Ignores NeoRibbon's own QShortcut / menu actions / commands so rebinding
    does not false-positive on NeoRibbon itself.
    """
    target = normalize_shortcut(sequence)
    if not target:
        return []

    conflicts: list[str] = []
    seen: set[str] = set()

    def _add(label: str) -> None:
        key = label.casefold()
        if key in seen:
            return
        seen.add(key)
        conflicts.append(label)

    def _matches_target(seq) -> bool:
        return sequences_match(seq, target)

    if mw is not None:
        try:
            for sc in list(mw.findChildren(QShortcut)):
                try:
                    name = sc.objectName() or ""
                except Exception:
                    name = ""
                if _is_our_shortcut_name(name):
                    continue
                try:
                    if hasattr(sc, "isEnabled") and not sc.isEnabled():
                        continue
                except Exception:
                    pass
                try:
                    key = sc.key()
                except Exception:
                    continue
                if _matches_target(key):
                    _add(f"QShortcut ({name or 'unnamed'})")
        except Exception:
            pass

        try:
            for action in list(mw.findChildren(QAction)):
                try:
                    name = action.objectName() or ""
                except Exception:
                    name = ""
                try:
                    text = action.text() or ""
                except Exception:
                    text = ""
                if _is_our_action_name(name, text):
                    continue
                for seq in _iter_action_sequences(action):
                    if _matches_target(seq):
                        _add(f"Action: {_action_label(action)}")
                        break
        except Exception:
            pass

    try:
        names = list(Gui.listCommands())
    except Exception:
        try:
            names = list(Gui.Command.listAll())
        except Exception:
            names = []

    for cmd_name in names:
        if cmd_name in NEORIBBON_COMMAND_NAMES:
            continue
        try:
            cmd = Gui.Command.get(cmd_name)
        except Exception:
            continue
        if cmd is None:
            continue
        accel = ""
        try:
            if hasattr(cmd, "getInfo"):
                info = cmd.getInfo() or {}
                if isinstance(info, dict):
                    for key in ("accel", "Accel", "shortcut", "Shortcut"):
                        value = info.get(key)
                        if value:
                            accel = str(value).strip()
                            break
        except Exception:
            accel = ""
        if not accel and hasattr(cmd, "getShortcut"):
            try:
                accel = str(cmd.getShortcut() or "").strip()
            except Exception:
                accel = ""
        if accel and _matches_target(accel):
            _add(f"Command: {cmd_name}")

    return conflicts
