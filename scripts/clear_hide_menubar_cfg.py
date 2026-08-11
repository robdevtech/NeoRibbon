#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""
Flip HideMenubar=0 in FreeCAD user.cfg while FreeCAD is fully quit.

Usage:
  python3 scripts/clear_hide_menubar_cfg.py
  python3 scripts/clear_hide_menubar_cfg.py /path/to/user.cfg

Default Flatpak path:
  ~/.var/app/org.freecad.FreeCAD/config/FreeCAD/v1-1/user.cfg
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

DEFAULT_FLATPAK = (
    Path.home()
    / ".var/app/org.freecad.FreeCAD/config/FreeCAD/v1-1/user.cfg"
)
DEFAULT_NATIVE = Path.home() / ".config/FreeCAD/v1-1/user.cfg"


def _candidate_paths() -> list[Path]:
    paths: list[Path] = []
    if len(sys.argv) > 1:
        paths.append(Path(sys.argv[1]).expanduser())
    paths.extend([DEFAULT_FLATPAK, DEFAULT_NATIVE])
    # Older layouts without v1-1
    paths.append(Path.home() / ".var/app/org.freecad.FreeCAD/config/FreeCAD/user.cfg")
    paths.append(Path.home() / ".config/FreeCAD/user.cfg")
    return paths


def _neo_ribbon_span(text: str) -> tuple[int, int] | None:
    """Return [start, end) of the outer NeoRibbon FCParamGroup (handles nesting)."""
    start = text.find('<FCParamGroup Name="NeoRibbon">')
    if start < 0:
        return None
    pos = start + len('<FCParamGroup Name="NeoRibbon">')
    depth = 1
    open_tag = re.compile(r"<FCParamGroup\b")
    close_tag = re.compile(r"</FCParamGroup>")
    while depth > 0 and pos < len(text):
        m_open = open_tag.search(text, pos)
        m_close = close_tag.search(text, pos)
        if m_close is None:
            return None
        if m_open is not None and m_open.start() < m_close.start():
            depth += 1
            pos = m_open.end()
        else:
            depth -= 1
            pos = m_close.end()
            if depth == 0:
                return start, pos
    return None


def clear_hide_menubar(cfg_path: Path) -> bool:
    text = cfg_path.read_text(encoding="utf-8", errors="replace")
    span = _neo_ribbon_span(text)
    if span is None:
        print(f"No NeoRibbon group in {cfg_path}")
        return False
    start, end = span
    group = text[start:end]
    new_group, n = re.subn(
        r'(<FCBool Name="HideMenubar" Value=")1("/>)',
        r"\g<1>0\2",
        group,
        count=1,
    )
    if n == 0:
        if 'Name="HideMenubar" Value="0"' in group:
            print(f"HideMenubar already 0 in {cfg_path}")
            return True
        print(f"HideMenubar entry not found (or not Value=1) in {cfg_path}")
        return False
    new_text = text[:start] + new_group + text[end:]
    backup = cfg_path.with_suffix(cfg_path.suffix + ".bak-neoribbon")
    backup.write_text(text, encoding="utf-8")
    cfg_path.write_text(new_text, encoding="utf-8")
    print(f"Set HideMenubar=0 in {cfg_path} (backup: {backup})")
    return True


def main() -> int:
    print("Quit FreeCAD fully before editing user.cfg (otherwise it may overwrite).")
    for path in _candidate_paths():
        if path.is_file():
            return 0 if clear_hide_menubar(path) else 1
    print("No user.cfg found. Pass the path explicitly.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
